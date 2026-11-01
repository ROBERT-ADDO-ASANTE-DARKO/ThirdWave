// routing_screen.dart — Phase 4 feature #5, Safer Routing During Heavy
// Rainfall. Mirrors streamlit_app/features/citizen_routing.py: compares a
// fastest-by-distance route against a risk-weighted "safer" route on the
// same precomputed road graph (GET /routing/safer-route, backed by
// backend/route_engine.py). Both routes are always shown side by side --
// never just the "safer" one alone -- so you can see the tradeoff.
//
// This is the one feature that actually needs a map (see project chat
// history: the Mapbox-vs-flutter_map decision made for feature #4's Alert
// screen, which deliberately shipped without one). flutter_map is free,
// OSM-tile-based, pure Dart -- no native SDK, no metered billing, and no
// extra load on this dev machine's constrained Gradle build.
//
// The map is centered on the pilot district by default, not conditional
// on having a route -- orients the citizen before they've searched
// anything (same change made to My Zone).
//
// _mapWidgetReady below exists because mounting the map unconditionally
// (rather than gated on a result) turned out NOT to fully dodge
// flutter_map 8.3.2's "setState called during build" bug -- it still hit
// live, triggered by switching to this tab at all: that switch is itself
// a setState()-driven rebuild in the nav shell, and FlutterMap's very
// first mount happening inside ANY ancestor's active build (not just one
// this screen's own setState produced) is what actually triggers the
// bug. Deferring the first mount by one frame via this screen's own
// initState/addPostFrameCallback -- independent of whatever caused the
// screen to appear -- is the fix that actually holds.

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../services/api_client.dart';
import '../widgets/citizen_app_bar.dart';

// Pilot district bbox centroid (risk_engine/channel_encroachment_timeseries.py's
// own computed extent) -- the default map view before any route is found.
const _pilotCenter = LatLng(5.541198730000104, -0.30136108399989303);
const _fastColor = Color(0xFFC1621B);
const _safeColor = Color(0xFF1B7A9E);

class RoutingScreen extends StatefulWidget {
  final ApiClient apiClient;
  const RoutingScreen({super.key, required this.apiClient});

  @override
  State<RoutingScreen> createState() => _RoutingScreenState();
}

enum _OriginMode { address, currentLocation }

class _RoutingScreenState extends State<RoutingScreen> {
  final _originController = TextEditingController();
  final _destController = TextEditingController();
  final _mapController = MapController();

  _OriginMode _originMode = _OriginMode.address;
  bool _loading = false;
  String? _error;
  Map<String, dynamic>? _result;
  LatLng? _originLatLng;
  LatLng? _destLatLng;
  bool _mapWidgetReady = false;

  // Opt-in "Start navigation": live GPS position/heading/speed while the
  // citizen is actually driving/walking the found route. Off by default --
  // only requests a continuous location stream once the user explicitly
  // asks for it, same permission flow as "Use my location" above.
  StreamSubscription<Position>? _positionSub;
  bool _navigating = false;
  LatLng? _liveLatLng;
  double? _liveHeadingDeg;
  double? _liveSpeedKmh;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) setState(() => _mapWidgetReady = true);
    });
  }

  @override
  void dispose() {
    _positionSub?.cancel();
    super.dispose();
  }

  List<Polyline> get _polylines {
    if (_result == null) return [];
    final fast = _result!['fast_route'] as Map<String, dynamic>;
    final safe = _result!['safe_route'] as Map<String, dynamic>;
    return [
      Polyline(points: _pathPoints(fast), color: _fastColor, strokeWidth: 5),
      Polyline(points: _pathPoints(safe), color: _safeColor, strokeWidth: 5),
    ];
  }

  List<Marker> get _markers {
    final markers = <Marker>[];
    if (_originLatLng != null) {
      markers.add(Marker(point: _originLatLng!, width: 32, height: 32,
          child: const Icon(Icons.trip_origin, color: Color(0xFF1E8A4C), size: 28)));
    }
    if (_destLatLng != null) {
      markers.add(Marker(point: _destLatLng!, width: 32, height: 32,
          child: const Icon(Icons.flag, color: Color(0xFF0B2545), size: 28)));
    }
    if (_result != null) {
      final activeIncidents = (_result!['active_incidents'] as List).cast<Map<String, dynamic>>();
      for (final inc in activeIncidents) {
        markers.add(Marker(
          point: LatLng((inc['lat'] as num).toDouble(), (inc['lon'] as num).toDouble()),
          width: 32, height: 32,
          child: const Icon(Icons.warning_amber, color: Color(0xFFB0241D), size: 26),
        ));
      }
    }
    if (_navigating && _liveLatLng != null) {
      markers.add(Marker(
        point: _liveLatLng!,
        width: 40, height: 40,
        child: Transform.rotate(
          angle: (_liveHeadingDeg ?? 0) * math.pi / 180,
          child: const Icon(Icons.navigation, color: _safeColor, size: 34),
        ),
      ));
    }
    return markers;
  }

  Future<void> _toggleNavigation() async {
    if (_navigating) {
      await _stopNavigation();
      return;
    }
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        setState(() => _error = 'Location services are off.');
        return;
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
        setState(() => _error = 'Location permission denied.');
        return;
      }
    } catch (e) {
      setState(() => _error = 'Could not start navigation: $e');
      return;
    }
    setState(() { _navigating = true; _error = null; });
    _positionSub = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, distanceFilter: 3),
    ).listen(_onPosition);
  }

  Future<void> _stopNavigation() async {
    await _positionSub?.cancel();
    _positionSub = null;
    if (mounted) setState(() => _navigating = false);
  }

  void _onPosition(Position pos) {
    if (!mounted) return;
    setState(() {
      _liveLatLng = LatLng(pos.latitude, pos.longitude);
      if (!pos.heading.isNaN && pos.heading >= 0) _liveHeadingDeg = pos.heading;
      if (!pos.speed.isNaN && pos.speed >= 0) _liveSpeedKmh = pos.speed * 3.6;
    });
    if (_mapWidgetReady) {
      final zoom = _mapController.camera.zoom;
      _mapController.move(_liveLatLng!, zoom < 15 ? 16 : zoom);
    }
  }

  // Which of the two found routes the live position is currently closest
  // to -- a cheap nearest-vertex snap, not a full map-matching algorithm,
  // but good enough at the road-network resolution this pilot district
  // uses.
  String? _activeRouteLabel(LatLng point) {
    if (_result == null) return null;
    const onRouteMeters = 40.0;
    final fastDist = _minDistanceToPath(point, _pathPoints(_result!['fast_route']));
    final safeDist = _minDistanceToPath(point, _pathPoints(_result!['safe_route']));
    if (fastDist == null && safeDist == null) return null;
    final onFast = fastDist != null && (safeDist == null || fastDist <= safeDist);
    final nearest = onFast ? fastDist : safeDist!;
    final label = onFast ? 'Fastest route' : 'Safer route';
    return nearest <= onRouteMeters ? 'On: $label' : 'Off route (nearest: $label)';
  }

  double? _minDistanceToPath(LatLng point, List<LatLng> path) {
    if (path.isEmpty) return null;
    const distance = Distance();
    var best = double.infinity;
    for (final p in path) {
      final d = distance.as(LengthUnit.Meter, point, p);
      if (d < best) best = d;
    }
    return best;
  }

  Future<Map<String, double>?> _resolveOrigin() async {
    if (_originMode == _OriginMode.currentLocation) {
      try {
        if (!await Geolocator.isLocationServiceEnabled()) {
          setState(() => _error = 'Location services are off.');
          return null;
        }
        var permission = await Geolocator.checkPermission();
        if (permission == LocationPermission.denied) {
          permission = await Geolocator.requestPermission();
        }
        if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
          setState(() => _error = 'Location permission denied.');
          return null;
        }
        final pos = await Geolocator.getCurrentPosition();
        return {'lat': pos.latitude, 'lon': pos.longitude};
      } catch (e) {
        setState(() => _error = 'Could not get location: $e');
        return null;
      }
    }
    final address = _originController.text.trim();
    if (address.isEmpty) return null;
    final resp = await widget.apiClient.get('/geocode', query: {'address': address});
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    if (body['error'] != null) return null;
    return {'lat': (body['lat'] as num).toDouble(), 'lon': (body['lon'] as num).toDouble()};
  }

  Future<Map<String, double>?> _resolveDest() async {
    final address = _destController.text.trim();
    if (address.isEmpty) return null;
    final resp = await widget.apiClient.get('/geocode', query: {'address': address});
    final body = jsonDecode(resp.body) as Map<String, dynamic>;
    if (body['error'] != null) return null;
    return {'lat': (body['lat'] as num).toDouble(), 'lon': (body['lon'] as num).toDouble()};
  }

  Future<void> _findRoutes() async {
    if (_navigating) await _stopNavigation();
    setState(() { _loading = true; _error = null; _result = null; });
    try {
      final o = await _resolveOrigin();
      final d = await _resolveDest();
      if (o == null) {
        setState(() => _error = "Couldn't get the 'From' location -- detect your location or type an address.");
        return;
      }
      if (d == null) {
        setState(() => _error = "Couldn't find the 'To' address.");
        return;
      }
      final resp = await widget.apiClient.get('/routing/safer-route', query: {
        'olat': o['lat'].toString(), 'olon': o['lon'].toString(),
        'dlat': d['lat'].toString(), 'dlon': d['lon'].toString(),
      });
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      if (body['error'] != null) {
        setState(() => _error = body['error'] as String);
        return;
      }
      setState(() {
        _result = body;
        _originLatLng = LatLng(o['lat']!, o['lon']!);
        _destLatLng = LatLng(d['lat']!, d['lon']!);
      });
      if (_mapWidgetReady) {
        WidgetsBinding.instance.addPostFrameCallback((_) => _fitBounds());
      }
    } catch (e) {
      setState(() => _error = 'Could not reach backend: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  void _fitBounds() {
    if (_originLatLng == null || _destLatLng == null) return;
    final points = [
      _originLatLng!, _destLatLng!,
      ..._pathPoints(_result!['fast_route']),
      ..._pathPoints(_result!['safe_route']),
    ];
    final bounds = LatLngBounds.fromPoints(points);
    _mapController.fitCamera(CameraFit.bounds(bounds: bounds, padding: const EdgeInsets.all(40)));
  }

  List<LatLng> _pathPoints(Map<String, dynamic> route) {
    final path = (route['path'] as List).cast<List>();
    return path.map((p) => LatLng((p[0] as num).toDouble(), (p[1] as num).toDouble())).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const CitizenAppBar(eyebrow: 'Routing', title: 'Safer Routing'),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 24),
        children: [
          const Text(
            "Compares the fastest route against a risk-weighted route that prefers lower-vulnerability "
            "zones and detours around currently verified active incidents. Always shown side by side, "
            "not just the 'safer' route alone, so you can see the tradeoff yourself.",
            style: TextStyle(color: Colors.grey, fontSize: 12),
          ),
          const SizedBox(height: 12),
          SegmentedButton<_OriginMode>(
            segments: const [
              ButtonSegment(value: _OriginMode.address, label: Text('Type address')),
              ButtonSegment(value: _OriginMode.currentLocation, label: Text('My location')),
            ],
            selected: {_originMode},
            onSelectionChanged: (s) => setState(() => _originMode = s.first),
          ),
          const SizedBox(height: 8),
          if (_originMode == _OriginMode.address)
            TextField(
              controller: _originController,
              decoration: const InputDecoration(labelText: 'From', hintText: 'e.g. Kwame Nkrumah Circle'),
            ),
          const SizedBox(height: 8),
          TextField(
            controller: _destController,
            decoration: const InputDecoration(labelText: 'To', hintText: 'e.g. Kaneshie Market'),
            onSubmitted: (_) => _findRoutes(),
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _loading ? null : _findRoutes,
            child: _loading ? const CircularProgressIndicator() : const Text('Find routes'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
          if (_result != null) ...[
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _toggleNavigation,
              icon: Icon(_navigating ? Icons.stop_circle_outlined : Icons.navigation_outlined),
              label: Text(_navigating ? 'Stop navigation' : 'Start navigation'),
            ),
          ],
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: SizedBox(
              height: 320,
              child: Stack(
                children: [
                  !_mapWidgetReady
                      ? const ColoredBox(color: Color(0xFFE6ECEF))
                      : FlutterMap(
                    mapController: _mapController,
                    options: const MapOptions(initialCenter: _pilotCenter, initialZoom: 12),
                    children: [
                      TileLayer(
                        urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                        userAgentPackageName: 'com.thirdwave.citizen',
                      ),
                      PolylineLayer(polylines: _polylines),
                      MarkerLayer(markers: _markers),
                    ],
                  ),
                  if (_navigating && _liveLatLng != null)
                    Positioned(
                      top: 10, left: 10,
                      child: _NavHud(
                        speedKmh: _liveSpeedKmh,
                        routeLabel: _activeRouteLabel(_liveLatLng!),
                      ),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Wrap(spacing: 14, runSpacing: 4, children: [
            _Legend(color: _fastColor, label: 'Fastest route'),
            _Legend(color: _safeColor, label: 'Safer route'),
            _Legend(color: Color(0xFF1E8A4C), label: 'From'),
            _Legend(color: Color(0xFF0B2545), label: 'To'),
            _Legend(color: Color(0xFFB0241D), label: 'Active incident'),
          ]),
          if (_result != null) _RouteResultView(result: _result!),
        ],
      ),
    );
  }
}

class _RouteResultView extends StatelessWidget {
  final Map<String, dynamic> result;

  const _RouteResultView({required this.result});

  @override
  Widget build(BuildContext context) {
    final fast = result['fast_route'] as Map<String, dynamic>;
    final safe = result['safe_route'] as Map<String, dynamic>;
    final activeIncidents = (result['active_incidents'] as List).cast<Map<String, dynamic>>();
    final fastHits = (fast['incidents_near'] as List).cast<Map<String, dynamic>>();
    final safeHits = (safe['incidents_near'] as List).cast<Map<String, dynamic>>();
    final sameRoute = result['same_route'] == true;
    final snapWarning = result['snap_warning'] == true;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              Expanded(child: _StatTile(
                label: 'Fastest route', value: '${fast['distance_km']} km',
                sub: fast['avg_zone_score'] != null ? 'avg zone score ${fast['avg_zone_score']}' : 'no zone data',
                color: _fastColor,
              )),
              Expanded(child: _StatTile(
                label: 'Safer route', value: '${safe['distance_km']} km',
                sub: safe['avg_zone_score'] != null ? 'avg zone score ${safe['avg_zone_score']}' : 'no zone data',
                color: _safeColor,
              )),
              Expanded(child: _StatTile(
                label: 'Extra distance', value: '${result['extra_km'] >= 0 ? '+' : ''}${result['extra_km']} km',
                sub: null, color: Colors.grey,
              )),
            ]),
          ),
        ),
        if (sameRoute) ...[
          const SizedBox(height: 8),
          const Text(
            'The fastest route and the safer route are the same road here -- no lower-risk alternative exists.',
            style: TextStyle(color: Color(0xFF166534)),
          ),
        ],
        if (snapWarning) ...[
          const SizedBox(height: 8),
          Text(
            "One of your points is >${(0.3 * 1000).toStringAsFixed(0)}m from the nearest road in the pilot "
            "district's mapped network -- the route shown actually starts/ends from the nearest mapped road, "
            "not the exact pin. This usually means that point falls outside the pilot district's coverage area.",
            style: const TextStyle(color: Color(0xFF8A5B07)),
          ),
        ],
        if (activeIncidents.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text('Active incidents along these routes', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          Text(
            "${activeIncidents.length} currently verified active incident(s) in the pilot district. The "
            "safer route's cost includes a heavy penalty for road segments within ~200m of any of them -- "
            "this is what turns a verified citizen report into an actual detour, not just a marker on a map.",
            style: const TextStyle(fontSize: 12, color: Colors.grey),
          ),
          const SizedBox(height: 8),
          Text(
            fastHits.isNotEmpty
                ? 'Fastest route passes within ~200m of ${fastHits.length} active incident(s).'
                : "Fastest route doesn't pass near any active incident.",
            style: TextStyle(color: fastHits.isNotEmpty ? const Color(0xFF8A5B07) : const Color(0xFF166534)),
          ),
          Text(
            safeHits.isNotEmpty
                ? 'Safer route still passes within ~200m of ${safeHits.length} active incident(s) -- no clear alternative avoids it.'
                : 'Safer route avoids all currently active incidents.',
            style: TextStyle(color: safeHits.isNotEmpty ? const Color(0xFF8A5B07) : const Color(0xFF166534)),
          ),
        ] else ...[
          const SizedBox(height: 8),
          const Text(
            'No currently active, verified incidents -- the safer route above reflects only the static '
            'vulnerability grid.',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ],
      ],
    );
  }
}

class _NavHud extends StatelessWidget {
  final double? speedKmh;
  final String? routeLabel;
  const _NavHud({required this.speedKmh, required this.routeLabel});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(12),
        boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            speedKmh != null ? '${speedKmh!.toStringAsFixed(0)} km/h' : '-- km/h',
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18, color: Color(0xFF0B2545)),
          ),
          if (routeLabel != null)
            Text(routeLabel!, style: const TextStyle(fontSize: 11, color: Colors.grey)),
        ],
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  final Color color;
  final String label;
  const _Legend({required this.color, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(width: 9, height: 9, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
      const SizedBox(width: 5),
      Text(label, style: const TextStyle(fontSize: 11, color: Colors.grey, fontWeight: FontWeight.w600)),
    ]);
  }
}

class _StatTile extends StatelessWidget {
  final String label;
  final String value;
  final String? sub;
  final Color color;
  const _StatTile({required this.label, required this.value, required this.sub, required this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.grey, fontSize: 12)),
        Text(value, style: Theme.of(context).textTheme.titleMedium?.copyWith(color: color, fontWeight: FontWeight.bold)),
        if (sub != null) Text(sub!, style: const TextStyle(fontSize: 11, color: Colors.grey)),
      ],
    );
  }
}
