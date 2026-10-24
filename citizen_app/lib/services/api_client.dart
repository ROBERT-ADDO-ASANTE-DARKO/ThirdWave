// api_client.dart — thin wrapper around the backend base URL, same
// local-dev reality as push_test_stub: the phone can't reach the
// backend via `localhost`, it needs either this PC's LAN IP (same WiFi)
// or `127.0.0.1` tunneled over USB via `adb reverse tcp:8000 tcp:8000`.
// Persisted so it survives app restarts instead of being re-typed.

import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiClient {
  static const _prefsKey = 'backend_base_url';
  static const defaultBaseUrl = 'http://127.0.0.1:8000';

  Future<String> getBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_prefsKey) ?? defaultBaseUrl;
  }

  Future<void> setBaseUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsKey, url);
  }

  Future<http.Response> get(String path, {Map<String, String>? query}) async {
    final base = await getBaseUrl();
    final uri = Uri.parse('$base$path').replace(queryParameters: query);
    return http.get(uri);
  }

  Future<http.Response> postJson(String path, Map<String, dynamic> body) async {
    final base = await getBaseUrl();
    return http.post(
      Uri.parse('$base$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
  }
}
