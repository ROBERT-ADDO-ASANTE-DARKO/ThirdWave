// home_screen.dart — Home tab, rebuilt to match the design concept
// Artifact's dashboard layout (https://claude.ai/artifact/EzDdSKqK3D8CYQFCLFS9yh):
// a "check your zone" entry point, a quick-actions grid to the other
// features, and an AI Assistant teaser -- not the bare debug panel this
// screen used to be.
//
// Honest adaptation, not a literal copy: the Artifact's mockup assumed a
// known "current zone" (hardcoded to Kwame Nkrumah Circle) already loaded
// on Home. This app has no location on startup -- the shared location
// permission plumbing was deliberately deferred to the screens that
// actually need it (see app-shell notes in MOBILE_APP_PHASES.md) -- so
// the entry card prompts the citizen to search or use their location via
// My Zone instead of faking a result.
//
// Hover-reveal descriptions AND a small looping animation on every card:
// MouseRegion only fires on pointer-based input (desktop/web), so this is
// purely additive on a touch device -- tapping to navigate works
// identically everywhere, there's just no hover state to ever trigger on
// a phone. Every animation is hand-drawn (CustomPainter) or composed from
// plain widgets rather than an image asset or network fetch, and only
// runs while hovered (_HoverAnim starts/stops its ticker on active, so
// idle cards never burn a frame).
//
// All six cards -- Check your flood risk, the four quick actions, and
// Ask the AI Assistant -- are the same full-width _InfoCard widget, each
// with its own illustration sized to match (~56px tall). An earlier pass
// kept the four quick actions in a 2-column GridView of smaller cards
// instead; that fixed-size cell was too cramped for an illustration to
// read as more than a tiny decoration, and looked inconsistent next to
// the two full-width cards -- this version fixes both at once.

import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/profile_controller.dart';
import '../services/push_service.dart';
import '../services/theme_controller.dart';
import '../theme.dart';
import '../widgets/citizen_app_bar.dart';
import '../widgets/feature_illustrations.dart';
import 'onboarding_screen.dart';

class HomeScreen extends StatefulWidget {
  final String reporterRef;
  final PushService pushService;
  final ApiClient apiClient;
  final void Function(int index) onNavigate;
  final ThemeController themeController;
  final ProfileController profileController;

  const HomeScreen({
    super.key,
    required this.reporterRef,
    required this.pushService,
    required this.apiClient,
    required this.onNavigate,
    required this.themeController,
    required this.profileController,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _urlController = TextEditingController();
  final _nameController = TextEditingController();
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
    _nameController.text = widget.profileController.name ?? '';
    _messageSub = widget.pushService.onForegroundMessage.listen((m) {
      setState(() {
        _received.insert(0, '${m.notification?.title ?? '(no title)'} -- ${m.notification?.body ?? '(no body)'}');
      });
    });
  }

  @override
  void dispose() {
    _messageSub?.cancel();
    _nameController.dispose();
    super.dispose();
  }

  void _replayTour() {
    Navigator.of(context).push(MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => OnboardingScreen(profileController: widget.profileController),
    ));
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

  String get _greeting {
    final h = DateTime.now().hour;
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: CitizenAppBar(eyebrow: 'ThirdWave · Accra Pilot', title: _greeting),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 24),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('APPEARANCE', style: TextStyle(
                    fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 0.8, color: Colors.grey,
                  )),
                  const SizedBox(height: 10),
                  SegmentedButton<ThemeMode>(
                    segments: const [
                      ButtonSegment(value: ThemeMode.light, icon: Icon(Icons.light_mode_outlined), label: Text('Light')),
                      ButtonSegment(value: ThemeMode.dark, icon: Icon(Icons.dark_mode_outlined), label: Text('Dark')),
                      ButtonSegment(value: ThemeMode.system, icon: Icon(Icons.phone_iphone), label: Text('System')),
                    ],
                    selected: {widget.themeController.mode},
                    onSelectionChanged: (s) => widget.themeController.setMode(s.first),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          ListenableBuilder(
            listenable: widget.profileController,
            builder: (context, _) => Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('PROFILE', style: TextStyle(
                      fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 0.8, color: Colors.grey,
                    )),
                    const SizedBox(height: 10),
                    TextField(
                      controller: _nameController,
                      decoration: const InputDecoration(hintText: 'Your name (optional)'),
                      onSubmitted: (v) => widget.profileController.setName(v),
                      onTapOutside: (_) => widget.profileController.setName(_nameController.text),
                    ),
                    const SizedBox(height: 4),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed: _replayTour,
                        icon: const Icon(Icons.replay, size: 16),
                        label: const Text('Replay app tour'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          _InfoCard(
            icon: Icons.place_outlined, baseColor: signalTeal,
            title: 'Check your flood risk',
            subtitle: 'Search an address or use your location',
            description: 'Look up any address or your current location to see its flood vulnerability score, '
                'what drives that score, and any officer-verified reports nearby.',
            onTap: () => widget.onNavigate(1),
            illustrationBuilder: (active) => ZoneScanIllustration(active: active),
          ),
          const SizedBox(height: 20),
          const Text('QUICK ACTIONS', style: TextStyle(
            fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 0.8, color: Colors.grey,
          )),
          const SizedBox(height: 10),
          _InfoCard(
            icon: Icons.camera_alt_outlined, baseColor: signalTeal,
            title: 'Report a flood',
            subtitle: 'Photo, AI draft, submit',
            description: 'Snap a photo, get an AI-drafted description, and submit a report that routes '
                "to your district's officers.",
            onTap: () => widget.onNavigate(2),
            illustrationBuilder: (active) => PulseRing(active: active, color: signalTeal, icon: Icons.camera_alt),
          ),
          const SizedBox(height: 12),
          _InfoCard(
            icon: Icons.water_drop_outlined, baseColor: signalTeal,
            title: 'Rainfall forecast',
            subtitle: '7-day forecast for your zone',
            description: "See a 7-day forecast for your zone, charted against its warning and critical "
                "rainfall thresholds.",
            onTap: () => widget.onNavigate(3),
            illustrationBuilder: (active) => RainfallBars(active: active),
          ),
          const SizedBox(height: 12),
          _InfoCard(
            icon: Icons.warning_amber_outlined, baseColor: const Color(0xFFB8860B),
            title: 'Check alerts',
            subtitle: 'Zone risk + rainfall + incidents',
            description: 'Combine your zone\'s risk, live rainfall, and nearby verified incidents into '
                'one on-demand check.',
            onTap: () => widget.onNavigate(4),
            illustrationBuilder: (active) => PulseRing(active: active, color: const Color(0xFFB8860B), icon: Icons.warning_amber),
          ),
          const SizedBox(height: 12),
          _InfoCard(
            icon: Icons.alt_route_outlined, baseColor: signalTeal,
            title: 'Plan a route',
            subtitle: 'Fastest vs. safer route',
            description: 'Compare the fastest route against a safer one that avoids high-risk zones and '
                'active incidents.',
            onTap: () => widget.onNavigate(5),
            illustrationBuilder: (active) => MiniMapIllustration(active: active),
          ),
          const SizedBox(height: 16),
          _InfoCard(
            icon: Icons.chat_bubble_outline, baseColor: steelBlue,
            title: 'Ask Tide',
            subtitle: 'Grounded in real flood data',
            description: 'Ask Tide, the AI Assistant, questions about flood risk in plain language -- answers '
                'are grounded in real data from the risk engine and live, officer-verified citizen reports, '
                'not guesses.',
            onTap: () => widget.onNavigate(6),
            illustrationBuilder: (active) => ChatBubbleIllustration(active: active, color: steelBlue),
          ),
          const SizedBox(height: 20),
          Theme(
            data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
            child: ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: const Text('Connection & notifications', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
              childrenPadding: const EdgeInsets.only(top: 8, bottom: 16),
              children: [
                const Text('Reporter ID (anonymous, persisted locally)', style: TextStyle(fontWeight: FontWeight.bold)),
                SelectableText(widget.reporterRef),
                const Divider(height: 24),
                const Text('Push notification status', style: TextStyle(fontWeight: FontWeight.bold)),
                Text(widget.pushService.status.name),
                if (widget.pushService.error != null) Text(widget.pushService.error!),
                TextButton(onPressed: _retryPush, child: const Text('Retry')),
                const Divider(height: 24),
                const Text('Backend base URL', style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                TextField(controller: _urlController),
                const SizedBox(height: 8),
                ElevatedButton(onPressed: _saveUrl, child: const Text('Save')),
                if (_status.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_status)),
                const Divider(height: 24),
                const Text('Received while app is open', style: TextStyle(fontWeight: FontWeight.bold)),
                ..._received.map((r) => Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Text(r))),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Full-width card: on hover, grows (AnimatedSize) to reveal a one-
/// sentence description and a small looping illustration below its
/// usual icon+title+subtitle row. All six Home cards -- Check your flood
/// risk, the four quick actions, and Ask the AI Assistant -- use this
/// same widget now, so every illustration gets the same real estate and
/// the same hover behavior (an earlier version kept the four quick
/// actions in a small fixed-size GridView cell instead, which was both
/// visually inconsistent with the two full-width cards and too cramped
/// for an illustration to read as more than a tiny decoration).
class _InfoCard extends StatefulWidget {
  final IconData icon;
  final Color baseColor;
  final String title;
  final String subtitle;
  final String description;
  final VoidCallback onTap;
  final Widget Function(bool active) illustrationBuilder;

  const _InfoCard({
    required this.icon, required this.baseColor, required this.title,
    required this.subtitle, required this.description, required this.onTap,
    required this.illustrationBuilder,
  });

  @override
  State<_InfoCard> createState() => _InfoCardState();
}

class _InfoCardState extends State<_InfoCard> {
  bool _hovering = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: widget.onTap,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: AnimatedSize(
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut,
              alignment: Alignment.topCenter,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    CircleAvatar(
                      radius: 20, backgroundColor: tintBackground(context, widget.baseColor),
                      child: Icon(widget.icon, color: widget.baseColor),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(widget.title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                          const SizedBox(height: 2),
                          Text(widget.subtitle, style: const TextStyle(color: Colors.grey, fontSize: 12.5)),
                        ],
                      ),
                    ),
                    Icon(_hovering ? Icons.arrow_forward : Icons.chevron_right, color: Colors.grey),
                  ]),
                  if (_hovering) ...[
                    const SizedBox(height: 10),
                    Text(widget.description, style: const TextStyle(fontSize: 12.5, height: 1.4)),
                    const SizedBox(height: 10),
                    widget.illustrationBuilder(_hovering),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

