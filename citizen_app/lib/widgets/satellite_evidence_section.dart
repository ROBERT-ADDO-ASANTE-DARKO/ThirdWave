// satellite_evidence_section.dart — real Sentinel-2 true-color imagery of
// a known encroachment hotspot within a district, attached to a zone
// lookup result's `satellite_evidence` list (backend/geo_data.py's
// _satellite_evidence_for_assembly, served from main.py's /evidence
// static mount). A FIXED reference site, not the citizen's exact
// searched location -- the caption says so explicitly, every time, so
// this is never mistaken for "here's a photo of your exact address."
//
// Shared between My Zone (address_vulnerability_screen.dart, alongside
// its inline map) and Alert (alert_screen.dart, which has no map at all
// -- a deliberate earlier scope cut -- so this is the first visual
// element there instead of "alongside" anything).
//
// Plain Image.network, no image-caching package: this app has none, and
// one evidence image per screen view doesn't need more than Flutter's
// own session-lifetime ImageCache already provides.

import 'package:flutter/material.dart';

import '../services/api_client.dart';

class SatelliteEvidenceSection extends StatelessWidget {
  final ApiClient apiClient;
  final List<Map<String, dynamic>> evidence;
  const SatelliteEvidenceSection({super.key, required this.apiClient, required this.evidence});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Satellite evidence', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 4),
        Text(
          'Known encroachment hotspot in this district -- not necessarily this exact point.',
          style: TextStyle(fontSize: 11, color: Colors.grey[600]),
        ),
        const SizedBox(height: 8),
        for (final item in evidence) ...[
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: FutureBuilder<String>(
              future: apiClient.imageUrl(item['url'] as String),
              builder: (context, snapshot) {
                if (!snapshot.hasData) {
                  return const SizedBox(
                    height: 180,
                    child: ColoredBox(color: Color(0xFFE6ECEF), child: Center(child: CircularProgressIndicator())),
                  );
                }
                return Image.network(
                  snapshot.data!,
                  height: 180,
                  width: double.infinity,
                  fit: BoxFit.cover,
                  loadingBuilder: (context, child, progress) {
                    if (progress == null) return child;
                    return const SizedBox(
                      height: 180,
                      child: ColoredBox(color: Color(0xFFE6ECEF), child: Center(child: CircularProgressIndicator())),
                    );
                  },
                  errorBuilder: (context, error, stackTrace) => const SizedBox.shrink(),
                );
              },
            ),
          ),
          const SizedBox(height: 4),
          Text(item['caption'] as String? ?? '', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}
