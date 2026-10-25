// rainfall_screen.dart — Phase 4 feature #3, Rainfall Forecast. Mirrors
// streamlit_app/features/citizen_forecast.py: address -> 7-day Open-Meteo
// forecast, 6h rolling sum charted against this zone's own warning/
// critical rainfall thresholds (GET /forecast/rainfall).
//
// Same honest scope limit as the Streamlit version: this is a
// rainfall-only read, not the full dual-factor (rainfall + river level)
// rule engine -- there's no river-level forecast source.

import 'dart:convert';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../services/api_client.dart';

class RainfallScreen extends StatefulWidget {
  final ApiClient apiClient;
  const RainfallScreen({super.key, required this.apiClient});

  @override
  State<RainfallScreen> createState() => _RainfallScreenState();
}

class _RainfallScreenState extends State<RainfallScreen> {
  final _addressController = TextEditingController();
  bool _loading = false;
  Map<String, dynamic>? _result;
  String? _networkError;

  Future<void> _getForecast() async {
    final address = _addressController.text.trim();
    if (address.isEmpty) return;
    setState(() { _loading = true; _result = null; _networkError = null; });
    try {
      final geo = await widget.apiClient.get('/geocode', query: {'address': address});
      final geoBody = jsonDecode(geo.body) as Map<String, dynamic>;
      if (geoBody['error'] != null) {
        setState(() => _networkError = "Couldn't find that address. Try a more specific landmark.");
        return;
      }
      final lat = (geoBody['lat'] as num).toDouble();
      final lon = (geoBody['lon'] as num).toDouble();

      final resp = await widget.apiClient.get('/forecast/rainfall', query: {
        'lat': lat.toString(), 'lon': lon.toString(),
      });
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      if (body['error'] != null) {
        setState(() => _networkError = body['error'] as String);
        return;
      }
      setState(() => _result = body);
    } catch (e) {
      setState(() => _networkError = 'Could not reach backend: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Rainfall Forecast')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            'A real numerical weather forecast (Open-Meteo) fed through this '
            "project's own zone thresholds. Rainfall-only: the live rule engine "
            'also needs a river-level forecast we don\'t have a source for.',
            style: TextStyle(color: Colors.grey, fontSize: 12),
          ),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: TextField(
              controller: _addressController,
              decoration: const InputDecoration(hintText: 'e.g. Kwame Nkrumah Circle'),
              onSubmitted: (_) => _getForecast(),
            )),
            const SizedBox(width: 8),
            ElevatedButton(onPressed: _loading ? null : _getForecast, child: const Text('Get forecast')),
          ]),
          const SizedBox(height: 16),
          if (_loading) const Center(child: CircularProgressIndicator()),
          if (_networkError != null) Text(_networkError!, style: const TextStyle(color: Colors.red)),
          if (_result != null) _ForecastView(result: _result!),
        ],
      ),
    );
  }
}

class _ForecastView extends StatelessWidget {
  final Map<String, dynamic> result;
  const _ForecastView({required this.result});

  Color get _statusColor => switch (result['status']) {
        'critical' => Colors.red,
        'warning' => const Color(0xFFB8860B),
        _ => Colors.green,
      };

  @override
  Widget build(BuildContext context) {
    final hourly = (result['hourly'] as List).cast<Map<String, dynamic>>();
    final warnMm = (result['warning_mm'] as num).toDouble();
    final critMm = (result['critical_mm'] as num).toDouble();
    final spots = <FlSpot>[
      for (var i = 0; i < hourly.length; i++) FlSpot(i.toDouble(), (hourly[i]['rolling_6h_mm'] as num).toDouble()),
    ];
    final maxY = [critMm, ...spots.map((s) => s.y)].reduce((a, b) => a > b ? a : b) * 1.15;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Zone: ${result['zone_id']} (vulnerability score ${result['vulnerability_score']})',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 12),
        SizedBox(
          height: 260,
          child: LineChart(LineChartData(
            minY: 0, maxY: maxY,
            titlesData: const FlTitlesData(
              topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
              rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
              bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
              leftTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 36)),
            ),
            gridData: const FlGridData(show: true, drawVerticalLine: false),
            borderData: FlBorderData(show: false),
            lineBarsData: [
              LineChartBarData(spots: spots, isCurved: false, color: const Color(0xFF1B7A9E),
                  barWidth: 2, dotData: const FlDotData(show: false)),
            ],
            extraLinesData: ExtraLinesData(horizontalLines: [
              HorizontalLine(y: warnMm, color: const Color(0xFFB8860B), strokeWidth: 1, dashArray: [6, 4],
                  label: HorizontalLineLabel(show: true, alignment: Alignment.topRight,
                      labelResolver: (_) => 'Warning ${warnMm.toStringAsFixed(0)}mm')),
              HorizontalLine(y: critMm, color: const Color(0xFFB0241D), strokeWidth: 1, dashArray: [6, 4],
                  label: HorizontalLineLabel(show: true, alignment: Alignment.topRight,
                      labelResolver: (_) => 'Critical ${critMm.toStringAsFixed(0)}mm')),
            ]),
          )),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: _statusColor.withValues(alpha: 0.12),
            border: Border.all(color: _statusColor),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(result['message'] as String, style: TextStyle(color: _statusColor)),
        ),
      ],
    );
  }
}
