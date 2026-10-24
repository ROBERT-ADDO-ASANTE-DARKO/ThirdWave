// report_screen.dart — Phase 4 feature #2, Crowdsourced Flood Reporting.
// Mirrors streamlit_app/features/citizen_report.py's flow: photo -> AI
// draft (editable, never auto-submitted) -> location -> submit. Backed by
// POST /reports/draft (backend/vlm_client.py, a faithful port of
// streamlit_app/vlm_client.py) and POST /reports.

import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_client.dart';

const _hazardTypes = ['flash_flood', 'urban_flood', 'river_flood'];

class ReportScreen extends StatefulWidget {
  final ApiClient apiClient;
  final String reporterRef;
  const ReportScreen({super.key, required this.apiClient, required this.reporterRef});

  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  final _picker = ImagePicker();
  final _descriptionController = TextEditingController();
  final _addressController = TextEditingController();

  XFile? _photo;
  Uint8List? _photoBytes;
  bool _draftLoading = false;
  Map<String, dynamic>? _draft;
  Uint8List? _annotatedBytes;
  String _hazard = _hazardTypes[0];

  double? _lat, _lon;
  String? _locationLabel;
  bool _locating = false;

  bool _submitting = false;
  String? _statusMessage;
  bool _statusIsError = false;

  Future<void> _pickPhoto(ImageSource source) async {
    final file = await _picker.pickImage(source: source, imageQuality: 85);
    if (file == null) return;
    final bytes = await file.readAsBytes();
    setState(() {
      _photo = file;
      _photoBytes = bytes;
      _draft = null;
      _annotatedBytes = null;
    });
  }

  Future<void> _draftWithAI() async {
    if (_photoBytes == null) return;
    setState(() {
      _draftLoading = true;
      _statusMessage = null;
    });
    try {
      final resp = await widget.apiClient.postMultipart(
        '/reports/draft',
        files: [MultipartFilePart('photo', _photoBytes!, _photo!.name)],
      );
      if (resp.statusCode != 200) {
        setState(() => _statusMessage = 'AI description unavailable (${resp.statusCode}). You can still describe it yourself below.');
        return;
      }
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      if (body['error'] != null) {
        setState(() => _statusMessage = 'AI description unavailable (${body['error']}). You can still describe it yourself below.');
        return;
      }
      setState(() {
        _draft = body;
        if (body['annotated_image_base64'] != null) {
          _annotatedBytes = base64Decode(body['annotated_image_base64'] as String);
        }
        if (body['shows_flooding'] == true) {
          _descriptionController.text = body['description'] as String? ?? '';
          final suggested = body['suggested_hazard_type'] as String?;
          if (suggested != null && _hazardTypes.contains(suggested)) _hazard = suggested;
        }
      });
    } catch (e) {
      setState(() => _statusMessage = 'AI description unavailable ($e). You can still describe it yourself below.');
    } finally {
      setState(() => _draftLoading = false);
    }
  }

  Future<void> _findAddress() async {
    final address = _addressController.text.trim();
    if (address.isEmpty) return;
    try {
      final resp = await widget.apiClient.get('/geocode', query: {'address': address});
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      if (body['error'] != null) {
        setState(() => _statusMessage = "Couldn't find that address. Try a more specific landmark, or use your location instead.");
        return;
      }
      setState(() {
        _lat = (body['lat'] as num).toDouble();
        _lon = (body['lon'] as num).toDouble();
        _locationLabel = body['resolved_address'] as String?;
        _statusMessage = null;
      });
    } catch (e) {
      setState(() => _statusMessage = 'Could not reach backend: $e');
    }
  }

  Future<void> _useCurrentLocation() async {
    setState(() => _locating = true);
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        setState(() => _statusMessage = 'Location services are off.');
        return;
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
        setState(() => _statusMessage = 'Location permission denied.');
        return;
      }
      final pos = await Geolocator.getCurrentPosition();
      setState(() {
        _lat = pos.latitude;
        _lon = pos.longitude;
        _locationLabel = 'Current location (${pos.latitude.toStringAsFixed(5)}, ${pos.longitude.toStringAsFixed(5)})';
        _statusMessage = null;
      });
    } catch (e) {
      setState(() => _statusMessage = 'Could not get location: $e');
    } finally {
      setState(() => _locating = false);
    }
  }

  Future<void> _submit() async {
    if (_lat == null || _lon == null) {
      setState(() { _statusMessage = 'Please set a location before submitting.'; _statusIsError = true; });
      return;
    }
    if (_descriptionController.text.trim().isEmpty) {
      setState(() { _statusMessage = 'Please describe what you see.'; _statusIsError = true; });
      return;
    }
    setState(() { _submitting = true; _statusMessage = null; });

    final fields = <String, String>{
      'lon': _lon!.toString(), 'lat': _lat!.toString(),
      'hazard_type': _hazard, 'description': _descriptionController.text.trim(),
      'reporter_ref': widget.reporterRef,
      'ai_assisted': (_draft != null).toString(),
    };
    if (_locationLabel != null) fields['location_label'] = _locationLabel!;
    final depth = _draft?['depth_estimate_m'] as Map<String, dynamic>?;
    if (depth != null) {
      fields['depth_lo_m'] = depth['low'].toString();
      fields['depth_hi_m'] = depth['high'].toString();
    }

    final files = <MultipartFilePart>[];
    if (_photoBytes != null) files.add(MultipartFilePart('photo', _photoBytes!, _photo!.name));
    if (_annotatedBytes != null) files.add(MultipartFilePart('annotated_photo', _annotatedBytes!, 'annotated.jpg'));

    try {
      final resp = await widget.apiClient.postMultipart('/reports', fields: fields, files: files);
      if (resp.statusCode != 200) {
        setState(() { _statusMessage = 'Submission failed (${resp.statusCode}): ${resp.body}'; _statusIsError = true; });
        return;
      }
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      final districtNote = body['district'] != null
          ? ' Routed to ${body['district']}.'
          : ' Outside the pilot district -- no officer queue covers this point yet.';
      setState(() {
        _statusMessage = 'Report ${body['id']} submitted -- Under Review.$districtNote';
        _statusIsError = false;
        _photo = null; _photoBytes = null; _draft = null; _annotatedBytes = null;
        _descriptionController.clear();
        _lat = null; _lon = null; _locationLabel = null;
        _addressController.clear();
        _hazard = _hazardTypes[0];
      });
    } catch (e) {
      setState(() { _statusMessage = 'Could not reach backend: $e'; _statusIsError = true; });
    } finally {
      setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Report a Flood')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('1. Add a photo', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: OutlinedButton.icon(
              onPressed: () => _pickPhoto(ImageSource.camera),
              icon: const Icon(Icons.camera_alt), label: const Text('Camera'),
            )),
            const SizedBox(width: 8),
            Expanded(child: OutlinedButton.icon(
              onPressed: () => _pickPhoto(ImageSource.gallery),
              icon: const Icon(Icons.photo_library), label: const Text('Gallery'),
            )),
          ]),
          if (_photoBytes != null) ...[
            const SizedBox(height: 12),
            Image.memory(_annotatedBytes ?? _photoBytes!, height: 220, fit: BoxFit.contain),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _draftLoading ? null : _draftWithAI,
              icon: _draftLoading
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.auto_awesome),
              label: const Text('Draft description with AI'),
            ),
          ],
          if (_draft != null) ...[
            const SizedBox(height: 8),
            if (_draft!['shows_flooding'] == false)
              Text("AI couldn't confirm this photo shows flooding: ${_draft!['note'] ?? ''}", style: const TextStyle(fontStyle: FontStyle.italic))
            else ...[
              Text('AI-suggested description -- check it\'s accurate before submitting:', style: const TextStyle(fontWeight: FontWeight.bold)),
              if (_draft!['depth_estimate_m'] != null)
                Text('Estimated depth: ${_draft!['depth_estimate_m']['low']}-${_draft!['depth_estimate_m']['high']}m (triage-quality estimate, not survey-grade)'),
            ],
          ],
          const Divider(height: 32),

          Text('2. Where is this?', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: TextField(controller: _addressController, decoration: const InputDecoration(hintText: 'Address or landmark'))),
            const SizedBox(width: 8),
            ElevatedButton(onPressed: _findAddress, child: const Text('Find')),
          ]),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _locating ? null : _useCurrentLocation,
            icon: _locating
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.my_location),
            label: const Text('Use my current location'),
          ),
          const SizedBox(height: 8),
          if (_locationLabel != null)
            Text('Location set: $_locationLabel', style: const TextStyle(color: Colors.green))
          else
            const Text('No location set yet.', style: TextStyle(color: Colors.grey)),
          const Divider(height: 32),

          Text('3. Confirm details and submit', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            initialValue: _hazard,
            items: _hazardTypes.map((h) => DropdownMenuItem(value: h, child: Text(h.replaceAll('_', ' ')))).toList(),
            onChanged: (v) => setState(() => _hazard = v ?? _hazard),
            decoration: const InputDecoration(labelText: 'What are you seeing?'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _descriptionController,
            maxLines: 3,
            decoration: const InputDecoration(
              labelText: 'Describe what you see',
              hintText: 'e.g. Water rising fast near the market, cars stuck',
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: _submitting ? null : _submit,
            child: _submitting ? const CircularProgressIndicator() : const Text('Submit Report'),
          ),
          if (_statusMessage != null) ...[
            const SizedBox(height: 12),
            Text(_statusMessage!, style: TextStyle(color: _statusIsError ? Colors.red : Colors.green)),
          ],
        ],
      ),
    );
  }
}
