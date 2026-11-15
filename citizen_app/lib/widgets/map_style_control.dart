// map_style_control.dart — shared map-tile style picker for every
// flutter_map instance in the app (My Zone, Routing's two maps). Mapbox's
// satellite/dark/terrain raster styles need the token
// backend/routers/config.py serves from ThirdWave/.env's MAPBOX_API_KEY
// (a pk.* token -- Mapbox's own "public, safe for client code" kind, so
// handing it to the app at runtime is normal use, just kept out of the
// app's source tree so it can rotate without a rebuild). The default
// Streets style stays plain OSM and needs no token, so the picker still
// works fine with Mapbox unconfigured -- the other options just grey out.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_client.dart';

enum MapStyleKind { streets, satellite, dark, terrain }

extension MapStyleKindDisplay on MapStyleKind {
  String get label => switch (this) {
        MapStyleKind.streets => 'Streets',
        MapStyleKind.satellite => 'Satellite',
        MapStyleKind.dark => 'Dark',
        MapStyleKind.terrain => 'Terrain',
      };

  IconData get icon => switch (this) {
        MapStyleKind.streets => Icons.map_outlined,
        MapStyleKind.satellite => Icons.satellite_alt_outlined,
        MapStyleKind.dark => Icons.dark_mode_outlined,
        MapStyleKind.terrain => Icons.terrain_outlined,
      };

  bool get needsMapboxToken => this != MapStyleKind.streets;
}

const _prefsKey = 'map_style_kind';

/// One global preference, not per-screen -- a citizen who picks Satellite
/// on My Zone almost certainly wants it on Routing too.
Future<MapStyleKind> loadMapStyle() async {
  final prefs = await SharedPreferences.getInstance();
  final name = prefs.getString(_prefsKey);
  return MapStyleKind.values.firstWhere((s) => s.name == name, orElse: () => MapStyleKind.streets);
}

Future<void> saveMapStyle(MapStyleKind style) async {
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString(_prefsKey, style.name);
}

// In-memory only, for the life of the app -- the token doesn't change
// mid-session, so there's no reason for every map screen to each hit
// /config/map-tiles on its own first build.
String? _cachedMapboxToken;
bool _mapboxTokenFetched = false;

Future<String?> fetchMapboxToken(ApiClient apiClient) async {
  if (_mapboxTokenFetched) return _cachedMapboxToken;
  try {
    final resp = await apiClient.get('/config/map-tiles');
    if (resp.statusCode == 200) {
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      _cachedMapboxToken = body['mapbox_token'] as String?;
    }
  } catch (_) {
    // Offline or backend unreachable -- picker just falls back to Streets.
  }
  _mapboxTokenFetched = true;
  return _cachedMapboxToken;
}

TileLayer tileLayerFor(MapStyleKind style, String? mapboxToken) {
  if (style == MapStyleKind.streets || mapboxToken == null) {
    return TileLayer(
      urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      userAgentPackageName: 'com.thirdwave.citizen',
    );
  }
  final styleId = switch (style) {
    MapStyleKind.satellite => 'satellite-streets-v12',
    MapStyleKind.dark => 'dark-v11',
    MapStyleKind.terrain => 'outdoors-v12',
    MapStyleKind.streets => 'streets-v12',
  };
  return TileLayer(
    urlTemplate:
        'https://api.mapbox.com/styles/v1/mapbox/$styleId/tiles/256/{z}/{x}/{y}@2x?access_token=$mapboxToken',
    userAgentPackageName: 'com.thirdwave.citizen',
  );
}

/// Small translucent-white-circle icon button, same treatment as
/// routing_screen's own map overlay buttons, that opens a style menu.
class MapStyleButton extends StatelessWidget {
  final MapStyleKind current;
  final ValueChanged<MapStyleKind> onChanged;
  final bool mapboxAvailable;
  const MapStyleButton({
    super.key,
    required this.current,
    required this.onChanged,
    required this.mapboxAvailable,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white.withValues(alpha: 0.92),
      shape: const CircleBorder(),
      elevation: 2,
      child: PopupMenuButton<MapStyleKind>(
        tooltip: 'Map style',
        initialValue: current,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        onSelected: onChanged,
        itemBuilder: (context) => MapStyleKind.values.map((style) {
          final disabled = style.needsMapboxToken && !mapboxAvailable;
          return PopupMenuItem(
            value: style,
            enabled: !disabled,
            child: Row(
              children: [
                Icon(style.icon, size: 18, color: disabled ? Colors.grey : const Color(0xFF0B2545)),
                const SizedBox(width: 10),
                Text(style.label, style: TextStyle(color: disabled ? Colors.grey : null)),
                if (style == current) ...[const Spacer(), const Icon(Icons.check, size: 16)],
              ],
            ),
          );
        }).toList(),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Icon(current.icon, color: const Color(0xFF0B2545), size: 24),
        ),
      ),
    );
  }
}
