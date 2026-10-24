// identity_service.dart — the anonymous reporter_ref Phase 3's backend
// made required on report submission. Generated once on first launch,
// persisted locally, never tied to a login -- see
// backend/MOBILE_APP_PHASES.md's Phase 3 section for why this is
// deliberately minimal, not real auth.

import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

class IdentityService {
  static const _prefsKey = 'reporter_ref';

  Future<String> getOrCreateReporterRef() async {
    final prefs = await SharedPreferences.getInstance();
    final existing = prefs.getString(_prefsKey);
    if (existing != null) return existing;

    final fresh = const Uuid().v4();
    await prefs.setString(_prefsKey, fresh);
    return fresh;
  }
}
