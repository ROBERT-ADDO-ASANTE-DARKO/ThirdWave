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

  /// Takes raw bytes rather than an image_picker XFile so this module
  /// doesn't need to depend on that package -- the caller reads the file
  /// itself and hands over bytes + a field name + filename.
  Future<http.Response> postMultipart(
    String path, {
    Map<String, String>? fields,
    List<MultipartFilePart>? files,
  }) async {
    final base = await getBaseUrl();
    final request = http.MultipartRequest('POST', Uri.parse('$base$path'));
    if (fields != null) request.fields.addAll(fields);
    if (files != null) {
      for (final f in files) {
        request.files.add(http.MultipartFile.fromBytes(f.field, f.bytes, filename: f.filename));
      }
    }
    final streamed = await request.send();
    return http.Response.fromStream(streamed);
  }
}

class MultipartFilePart {
  final String field;
  final List<int> bytes;
  final String filename;
  MultipartFilePart(this.field, this.bytes, this.filename);
}
