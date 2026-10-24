// home_screen.dart — app-shell status screen: shows the reporter_ref
// identity, push registration status, and lets you point the app at a
// different backend URL. Not one of the six citizen features -- this is
// the shell infrastructure they'll all sit on top of.

import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/push_service.dart';

class HomeScreen extends StatefulWidget {
  final String reporterRef;
  final PushService pushService;
  final ApiClient apiClient;

  const HomeScreen({
    super.key,
    required this.reporterRef,
    required this.pushService,
    required this.apiClient,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _urlController = TextEditingController();
  String _status = '';
  final List<String> _received = [];
  StreamSubscription? _messageSub;

  @override
  void initState() {
    super.initState();
    widget.apiClient.getBaseUrl().then((url) {
      _urlController.text = url;
      setState(() {});
    });
    _messageSub = widget.pushService.onForegroundMessage.listen((m) {
      setState(() {
        _received.insert(0, '${m.notification?.title ?? '(no title)'} -- ${m.notification?.body ?? '(no body)'}');
      });
    });
  }

  @override
  void dispose() {
    _messageSub?.cancel();
    super.dispose();
  }

  Future<void> _saveUrl() async {
    await widget.apiClient.setBaseUrl(_urlController.text);
    setState(() => _status = 'Saved.');
  }

  Future<void> _retryPush() async {
    setState(() => _status = 'Retrying...');
    await widget.pushService.init();
    if (widget.pushService.status == PushStatus.tokenObtained) {
      await widget.pushService.registerWithBackend();
    }
    setState(() => _status = 'Push status: ${widget.pushService.status.name}');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ThirdWave Citizen')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Reporter ID (anonymous, persisted locally)',
              style: TextStyle(fontWeight: FontWeight.bold)),
          SelectableText(widget.reporterRef),
          const Divider(height: 32),
          const Text('Push notification status', style: TextStyle(fontWeight: FontWeight.bold)),
          Text(widget.pushService.status.name),
          if (widget.pushService.error != null) Text(widget.pushService.error!),
          TextButton(onPressed: _retryPush, child: const Text('Retry')),
          const Divider(height: 32),
          const Text('Backend base URL', style: TextStyle(fontWeight: FontWeight.bold)),
          TextField(controller: _urlController),
          ElevatedButton(onPressed: _saveUrl, child: const Text('Save')),
          if (_status.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_status)),
          const Divider(height: 32),
          const Text('Received while app is open', style: TextStyle(fontWeight: FontWeight.bold)),
          ..._received.map((r) => Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text(r))),
        ],
      ),
    );
  }
}
