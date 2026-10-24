// push_service.dart — FCM token + registration, lifted from
// mobile/push_test_stub (the Phase 2 throwaway app that proved this
// round-trip actually works end to end). Guarded so a missing/misconfigured
// google-services.json degrades to "push disabled" instead of crashing
// the whole app -- every other screen should work independently of
// whether this app's Firebase registration is set up yet.
//
// lat/lon are omitted at registration time (left null) -- this app
// doesn't capture live GPS yet (see MOBILE_APP_PHASES.md's app-shell
// checklist); the first feature that does (High-Risk Zone Alert) should
// re-register with a real location once it has one.

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

import 'api_client.dart';

enum PushStatus { uninitialized, disabled, tokenObtained, registered, error }

class PushService {
  final ApiClient _api;
  PushService(this._api);

  PushStatus status = PushStatus.uninitialized;
  String? token;
  String? error;

  /// Foreground messages only -- background/terminated notifications are
  /// handled by the OS automatically (FCM's `notification` payload shows a
  /// system tray entry without this app needing to be running), same as
  /// push_test_stub found. This stream is for in-app display while open.
  Stream<RemoteMessage> get onForegroundMessage => FirebaseMessaging.onMessage;

  Future<void> init() async {
    try {
      await Firebase.initializeApp();
    } catch (e) {
      status = PushStatus.disabled;
      error = 'Firebase not configured: $e';
      return;
    }

    try {
      await FirebaseMessaging.instance.requestPermission();
      // Deliberately NOT register()/onRegistered despite the deprecation
      // warning: that API's onRegistered yields a Firebase Installation ID
      // (FID), not an FCM registration token -- confirmed by reading
      // firebase_messaging 17.0.0's own doc comments. backend/push.py sends
      // via Message(token=...) (a deliberate choice after Phase 2's
      // fid-vs-token bug, see MOBILE_APP_PHASES.md), which needs an actual
      // token. Switching here without migrating the backend to FID-based
      // direct-send would reintroduce that exact bug from the other
      // direction. getToken() still works; this is a known, accepted warning.
      // ignore: deprecated_member_use
      token = await FirebaseMessaging.instance.getToken();
      if (token == null) {
        status = PushStatus.error;
        error = 'No token returned';
        return;
      }
      status = PushStatus.tokenObtained;
    } catch (e) {
      status = PushStatus.error;
      error = '$e';
    }
  }

  Future<void> registerWithBackend() async {
    if (token == null) return;
    try {
      final resp = await _api.postJson('/devices/register', {
        'fcm_token': token,
        'platform': 'android',
        'lat': null,
        'lon': null,
      });
      status = resp.statusCode == 200 ? PushStatus.registered : PushStatus.error;
      if (resp.statusCode != 200) error = 'Backend returned ${resp.statusCode}: ${resp.body}';
    } catch (e) {
      status = PushStatus.error;
      error = 'Could not reach backend: $e';
    }
  }
}
