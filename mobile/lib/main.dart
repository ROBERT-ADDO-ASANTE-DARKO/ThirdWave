// push_test_stub -- a throwaway app, not the real Phase 4 Flutter client.
// Its only job: obtain a real FCM token on a real phone, register it with
// the ThirdWave backend's POST /devices/register, and show incoming
// notifications so a verify_report()/verify_bulk() call can be proven to
// actually reach this device. See backend/push.py and mobile/README.md.

import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  // Foreground notifications don't show a system tray banner by default on
  // Android -- they still arrive and trigger onMessage, which is what this
  // app displays instead, so nothing extra is needed here for that case.
  runApp(const PushTestApp());
}

class PushTestApp extends StatelessWidget {
  const PushTestApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ThirdWave push test',
      theme: ThemeData(colorSchemeSeed: const Color(0xFF1B7A9E), useMaterial3: true),
      home: const PushTestPage(),
    );
  }
}

class PushTestPage extends StatefulWidget {
  const PushTestPage({super.key});

  @override
  State<PushTestPage> createState() => _PushTestPageState();
}

class _PushTestPageState extends State<PushTestPage> {
  String? _token;
  String _status = 'Requesting notification permission...';
  final _backendUrlCtrl = TextEditingController(text: 'http://192.168.1.X:8000');
  // Defaults to Kwame Nkrumah Circle -- edit to test a location this
  // device's push radius (push.py's DEVICE_NOTIFY_RADIUS_KM, 1.5km
  // default) would or wouldn't cover.
  final _lonCtrl = TextEditingController(text: '-0.2153');
  final _latCtrl = TextEditingController(text: '5.5692');
  final List<String> _received = [];

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final settings = await FirebaseMessaging.instance.requestPermission();
    setState(() => _status = 'Permission: ${settings.authorizationStatus.name}');

    final token = await FirebaseMessaging.instance.getToken();
    setState(() {
      _token = token;
      _status = token != null ? 'Token obtained.' : 'No token -- check google-services.json is in place.';
    });

    FirebaseMessaging.onMessage.listen((RemoteMessage m) {
      setState(() {
        _received.insert(0, '${m.notification?.title ?? '(no title)'} -- ${m.notification?.body ?? '(no body)'}');
      });
    });
  }

  Future<void> _register() async {
    if (_token == null) return;
    setState(() => _status = 'Registering...');
    try {
      final resp = await http.post(
        Uri.parse('${_backendUrlCtrl.text}/devices/register'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'fcm_token': _token,
          'platform': 'android',
          'lat': double.tryParse(_latCtrl.text),
          'lon': double.tryParse(_lonCtrl.text),
        }),
      );
      setState(() => _status = resp.statusCode == 200
          ? 'Registered: ${resp.body}'
          : 'Backend returned ${resp.statusCode}: ${resp.body}');
    } catch (e) {
      setState(() => _status = 'Could not reach backend: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ThirdWave push test')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            Text(_status),
            const SizedBox(height: 12),
            const Text('FCM token', style: TextStyle(fontWeight: FontWeight.bold)),
            SelectableText(_token ?? '(waiting...)'),
            if (_token != null)
              TextButton(
                onPressed: () => Clipboard.setData(ClipboardData(text: _token!)),
                child: const Text('Copy token'),
              ),
            const Divider(height: 32),
            const Text('Backend base URL (this PC\'s LAN IP, not localhost)'),
            TextField(controller: _backendUrlCtrl),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: TextField(controller: _lonCtrl, decoration: const InputDecoration(labelText: 'lon'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _latCtrl, decoration: const InputDecoration(labelText: 'lat'))),
            ]),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: _token == null ? null : _register,
              child: const Text('Register device with backend'),
            ),
            const Divider(height: 32),
            const Text('Received while app is open', style: TextStyle(fontWeight: FontWeight.bold)),
            ..._received.map((r) => Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text(r))),
          ],
        ),
      ),
    );
  }
}
