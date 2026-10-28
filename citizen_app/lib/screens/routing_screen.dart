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

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../services/api_client.dart';

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
      WidgetsBinding.instance.addPostFrameCallback((_) => _fitBounds());
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
      appBar: AppBar(title: const Text('Safer Routing')),
      body: ListView(
        padding: const EdgeInsets.all(16),
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
          if (_result != null) _RouteResultView(
            result: _result!, originLatLng: _originLatLng!, destLatLng: _destLatLng!,
            mapController: _mapController,
          ),
        ],
      ),
    );
  }
}

class _RouteResultView extends StatelessWidget {
  final Map<String, dynamic> result;
  final LatLng originLatLng;
  final LatLng destLatLng;
  final MapController mapController;

  const _RouteResultView({
    required this.result, required this.originLatLng, required this.destLatLng,
    required this.mapController,
  });

  static const _fastColor = Color(0xFFC1621B);
  static const _safeColor = Color(0xFF1B7A9E);

  @override
  Widget build(BuildContext context) {
    final fast = result['fast_route'] as Map<String, dynamic>;
    final safe = result['safe_route'] as Map<String, dynamic>;
    final activeIncidents = (result['active_incidents'] as List).cast<Map<String, dynamic>>();
    final fastHits = (fast['incidents_near'] as List).cast<Map<String, dynamic>>();
    final safeHits = (safe['incidents_near'] as List).cast<Map<String, dynamic>>();
    final sameRoute = result['same_route'] == true;
    final snapWarning = result['snap_warning'] == true;

    final fastPoints = (fast['path'] as List).cast<List>()
        .map((p) => LatLng((p[0] as num).toDouble(), (p[1] as num).toDouble())).toList();
    final safePoints = (safe['path'] as List).cast<List>()
        .map((p) => LatLng((p[0] as num).toDouble(), (p[1] as num).toDouble())).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Divider(height: 24),
        Row(children: [
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
        if (sameRoute) ...[
          const SizedBox(height: 8),
          const Text(
            'The fastest route and the safer route are the same road here -- no lower-risk alternative exists.',
            style: TextStyle(color: Colors.green),
          ),
        ],
        if (snapWarning) ...[
          const SizedBox(height: 8),
          Text(
            "One of your points is >${(0.3 * 1000).toStringAsFixed(0)}m from the nearest road in the pilot "
            "district's mapped network -- the route shown actually starts/ends from the nearest mapped road, "
            "not the exact pin. This usually means that point falls outside the pilot district's coverage area.",
            style: const TextStyle(color: Color(0xFFB8860B)),
          ),
        ],
        const SizedBox(height: 12),
        SizedBox(
          height: 320,
          child: FlutterMap(
            mapController: mapController,
            options: MapOptions(initialCenter: originLatLng, initialZoom: 14),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.thirdwave.citizen',
              ),
              PolylineLayer(polylines: [
                Polyline(points: fastPoints, color: _fastColor, strokeWidth: 5),
                Polyline(points: safePoints, color: _safeColor, strokeWidth: 5),
              ]),
              MarkerLayer(markers: [
                Marker(point: originLatLng, width: 32, height: 32,
                    child: const Icon(Icons.trip_origin, color: Colors.green, size: 28)),
                Marker(point: destLatLng, width: 32, height: 32,
                    child: const Icon(Icons.flag, color: Colors.red, size: 28)),
                for (final inc in activeIncidents)
                  Marker(
                    point: LatLng((inc['lat'] as num).toDouble(), (inc['lon'] as num).toDouble()),
                    width: 32, height: 32,
                    child: const Icon(Icons.warning, color: Color(0xFF8B0000), size: 26),
                  ),
              ]),
            ],
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          '🟠 Fastest route · 🔵 Safer route · 🟢 From · 🚩 To · ⚠️ Active verified incident',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
        if (activeIncidents.isNotEmpty) ...[
          const Divider(height: 24),
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
                ? '🟠 Fastest route passes within ~200m of ${fastHits.length} active incident(s).'
                : "🟠 Fastest route doesn't pass near any active incident.",
            style: TextStyle(color: fastHits.isNotEmpty ? const Color(0xFFB8860B) : Colors.green),
          ),
          Text(
            safeHits.isNotEmpty
                ? '🔵 Safer route still passes within ~200m of ${safeHits.length} active incident(s) -- no clear alternative avoids it.'
                : '🔵 Safer route avoids all currently active incidents.',
            style: TextStyle(color: safeHits.isNotEmpty ? const Color(0xFFB8860B) : Colors.green),
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
