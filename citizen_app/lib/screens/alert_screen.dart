// alert_screen.dart — Phase 4 feature #4, High-Risk Zone Alert. Mirrors
// streamlit_app/features/citizen_alert.py: combines zone vulnerability,
// live rainfall, and nearby verified incidents into one on-demand check
// -- "you're in a High zone" alone isn't very actionable; "High zone,
// heavy rain forecast, AND a verified flood 400m away" is.
//
// No map (deliberate scope cut for this pass, see project chat history --
// Mapbox would be this project's first paid/metered dependency and a real
// risk on this dev machine's constrained RAM; a map is deferred to
// feature #5, Safer Routing, which actually needs one). This is the
// list/card version: same three signals, same alert logic, no map.
//
// Backend: no new aggregating endpoint, per MOBILE_APP_PHASES.md's
// feature #4 plan -- combines GET /zones/lookup-by-point (new, small:
// the existing /zones/lookup is address-only and GPS gives coordinates
// with no address text), GET /forecast/rainfall (feature #3), and the
// existing GET /incidents/nearby (Phase 1) client-side.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../services/api_client.dart';

const _nearbyRadiusKm = 1.5;

const _evacuationGuidance = {
  'flash_flood': 'Move to higher ground immediately -- flash floods can rise faster than you can outrun on '
      'foot or in a vehicle. Avoid walking or driving through moving water.',
  'urban_flood': 'Avoid the flooded area and nearby low-lying streets. If water is entering your building, '
      'move valuables and yourself to a higher floor.',
  'river_flood': 'Stay away from riverbanks and low bridges near the water. Follow any district officer '
      'instructions if the area is being evacuated.',
};
const _genericGuidance = 'Avoid the area. Do not attempt to walk or drive through standing water -- depth '
    'and current are hard to judge from a distance.';

class AlertScreen extends StatefulWidget {
  final ApiClient apiClient;
  const AlertScreen({super.key, required this.apiClient});

  @override
  State<AlertScreen> createState() => _AlertScreenState();
}

class _AlertScreenState extends State<AlertScreen> {
  final _addressController = TextEditingController();
  bool _loading = false;
  String? _error;

  String? _label;
  Map<String, dynamic>? _zone;
  double? _next6hRain;
  double? _warnMm;
  List<Map<String, dynamic>> _nearbyIncidents = [];

  Future<void> _checkAddress() async {
    final address = _addressController.text.trim();
    if (address.isEmpty) return;
    final geo = await widget.apiClient.get('/geocode', query: {'address': address});
    final geoBody = jsonDecode(geo.body) as Map<String, dynamic>;
    if (geoBody['error'] != null) {
      setState(() => _error = "Couldn't find that address. Try a more specific landmark.");
      return;
    }
    await _check(
      (geoBody['lat'] as num).toDouble(),
      (geoBody['lon'] as num).toDouble(),
      geoBody['resolved_address'] as String? ?? address,
    );
  }

  Future<void> _checkCurrentLocation() async {
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
      final pos = await Geolocator.getCurrentPosition();
      await _check(pos.latitude, pos.longitude, 'Detected location');
    } catch (e) {
      setState(() => _error = 'Could not get location: $e');
    }
  }

  Future<void> _check(double lat, double lon, String label) async {
    setState(() { _loading = true; _error = null; });
    try {
      final zoneResp = await widget.apiClient.get('/zones/lookup-by-point', query: {
        'lat': lat.toString(), 'lon': lon.toString(),
      });
      final zoneBody = jsonDecode(zoneResp.body) as Map<String, dynamic>;
      if (zoneBody['level'] == null) {
        setState(() {
          _error = '$label is outside the pilot district\'s coverage area.';
          _zone = null;
        });
        return;
      }

      final forecastResp = await widget.apiClient.get('/forecast/rainfall', query: {
        'lat': lat.toString(), 'lon': lon.toString(),
      });
      final forecastBody = jsonDecode(forecastResp.body) as Map<String, dynamic>;
      double? next6h;
      double? warnMm;
      if (forecastBody['error'] == null) {
        final hourly = (forecastBody['hourly'] as List).cast<Map<String, dynamic>>();
        next6h = (hourly[5]['rolling_6h_mm'] as num).toDouble(); // sum of hours 0-5 == "next 6h" from day start
        warnMm = (forecastBody['warning_mm'] as num).toDouble();
      }

      final nearbyResp = await widget.apiClient.get('/incidents/nearby', query: {
        'lat': lat.toString(), 'lon': lon.toString(), 'radius_km': _nearbyRadiusKm.toString(),
      });
      final nearby = (jsonDecode(nearbyResp.body) as List).cast<Map<String, dynamic>>();

      setState(() {
        _label = label;
        _zone = zoneBody;
        _next6hRain = next6h;
        _warnMm = warnMm;
        _nearbyIncidents = nearby;
      });
    } catch (e) {
      setState(() => _error = 'Could not reach backend: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('High-Risk Zone Alert')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            'Not a real push notification -- true "notify when entering a '
            'high-risk zone" needs background location, which this app '
            "doesn't do. This is an on-demand check combining this zone's "
            'vulnerability, live rainfall, and nearby verified incidents.',
            style: TextStyle(color: Colors.grey, fontSize: 12),
          ),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: TextField(
              controller: _addressController,
              decoration: const InputDecoration(hintText: 'Address or landmark'),
              onSubmitted: (_) => _checkAddress(),
            )),
            const SizedBox(width: 8),
            ElevatedButton(onPressed: _loading ? null : _checkAddress, child: const Text('Check')),
          ]),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _loading ? null : _checkCurrentLocation,
            icon: const Icon(Icons.my_location),
            label: const Text('Check my current location'),
          ),
          const SizedBox(height: 16),
          if (_loading) const Center(child: CircularProgressIndicator()),
          if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
          if (_zone != null) _AlertBody(
            label: _label!, zone: _zone!, next6hRain: _next6hRain, warnMm: _warnMm,
            nearbyIncidents: _nearbyIncidents,
          ),
        ],
      ),
    );
  }
}

class _AlertBody extends StatelessWidget {
  final String label;
  final Map<String, dynamic> zone;
  final double? next6hRain;
  final double? warnMm;
  final List<Map<String, dynamic>> nearbyIncidents;

  const _AlertBody({
    required this.label, required this.zone, required this.next6hRain,
    required this.warnMm, required this.nearbyIncidents,
  });

  @override
  Widget build(BuildContext context) {
    final level = zone['level'] as String;
    final isHighZone = level == 'High' || level == 'Very High';
    final isRainImminent = next6hRain != null && warnMm != null && next6hRain! >= warnMm! * 0.5;
    final exceedsWarning = next6hRain != null && warnMm != null && next6hRain! >= warnMm!;

    late final Color bannerColor;
    late final String bannerText;
    if (isHighZone && exceedsWarning) {
      bannerColor = Colors.red;
      bannerText = 'ALERT: $label is a $level zone, and ${next6hRain!.toStringAsFixed(0)}mm of rain is '
          "forecast in the next 6 hours (exceeds this zone's ${warnMm!.toStringAsFixed(0)}mm warning "
          'threshold). Avoid low-lying routes.';
    } else if (isHighZone && isRainImminent) {
      bannerColor = const Color(0xFFB8860B);
      bannerText = '$label is a $level zone, and moderate rain (${next6hRain!.toStringAsFixed(0)}mm) is '
          'forecast in the next 6 hours. Stay alert.';
    } else if (isHighZone) {
      bannerColor = const Color(0xFFB8860B);
      bannerText = '$label is a $level zone, but no significant rain is forecast in the next 6 hours right now.';
    } else if (isRainImminent) {
      bannerColor = Colors.blue;
      bannerText = '$label is a $level zone (not high-risk), but ${next6hRain!.toStringAsFixed(0)}mm of rain '
          'is forecast in the next 6 hours.';
    } else {
      bannerColor = Colors.green;
      bannerText = '$label is a $level zone, and no significant rain is forecast in the next 6 hours.';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Divider(height: 24),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: bannerColor.withValues(alpha: 0.12),
            border: Border.all(color: bannerColor),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(bannerText, style: TextStyle(color: bannerColor, fontWeight: FontWeight.bold)),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: _StatTile(label: 'Zone vulnerability', value: level)),
          Expanded(child: _StatTile(
            label: 'Next 6h rainfall',
            value: next6hRain != null ? '${next6hRain!.toStringAsFixed(0)}mm' : 'unavailable',
          )),
        ]),
        const Divider(height: 24),
        Text('Active flooding near you right now', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        if (nearbyIncidents.isEmpty)
          Text('No verified active incidents within ${_nearbyRadiusKm}km of this location right now.',
              style: const TextStyle(color: Colors.green))
        else
          ...nearbyIncidents.map((inc) {
            final hazard = inc['hazard_type'] as String;
            final distM = ((inc['distance_km'] as num).toDouble() * 1000).toStringAsFixed(0);
            final synthetic = inc['synthetic'] == true ? ' (demo)' : '';
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${hazard.replaceAll('_', ' ')}$synthetic -- ${distM}m away '
                      '(${inc['location_label'] ?? 'unnamed location'})',
                      style: const TextStyle(color: Colors.red, fontWeight: FontWeight.bold)),
                  Text(_evacuationGuidance[hazard] ?? _genericGuidance, style: const TextStyle(fontSize: 12)),
                ],
              ),
            );
          }),
      ],
    );
  }
}

class _StatTile extends StatelessWidget {
  final String label;
  final String value;
  const _StatTile({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.grey, fontSize: 12)),
        Text(value, style: Theme.of(context).textTheme.titleLarge),
      ],
    );
  }
}
