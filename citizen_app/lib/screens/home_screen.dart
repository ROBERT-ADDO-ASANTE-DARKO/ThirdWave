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
import '../services/push_service.dart';
import '../services/theme_controller.dart';
import '../theme.dart';
import '../widgets/citizen_app_bar.dart';

class HomeScreen extends StatefulWidget {
  final String reporterRef;
  final PushService pushService;
  final ApiClient apiClient;
  final void Function(int index) onNavigate;
  final ThemeController themeController;

  const HomeScreen({
    super.key,
    required this.reporterRef,
    required this.pushService,
    required this.apiClient,
    required this.onNavigate,
    required this.themeController,
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
          const SizedBox(height: 16),
          _InfoCard(
            icon: Icons.place_outlined, baseColor: signalTeal,
            title: 'Check your flood risk',
            subtitle: 'Search an address or use your location',
            description: 'Look up any address or your current location to see its flood vulnerability score, '
                'what drives that score, and any officer-verified reports nearby.',
            onTap: () => widget.onNavigate(1),
            illustrationBuilder: (active) => _ZoneScanIllustration(active: active),
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
            illustrationBuilder: (active) => _PulseRing(active: active, color: signalTeal, icon: Icons.camera_alt),
          ),
          const SizedBox(height: 12),
          _InfoCard(
            icon: Icons.water_drop_outlined, baseColor: signalTeal,
            title: 'Rainfall forecast',
            subtitle: '7-day forecast for your zone',
            description: "See a 7-day forecast for your zone, charted against its warning and critical "
                "rainfall thresholds.",
            onTap: () => widget.onNavigate(3),
            illustrationBuilder: (active) => _RainfallBars(active: active),
          ),
          const SizedBox(height: 12),
          _InfoCard(
            icon: Icons.warning_amber_outlined, baseColor: const Color(0xFFB8860B),
            title: 'Check alerts',
            subtitle: 'Zone risk + rainfall + incidents',
            description: 'Combine your zone\'s risk, live rainfall, and nearby verified incidents into '
                'one on-demand check.',
            onTap: () => widget.onNavigate(4),
            illustrationBuilder: (active) => _PulseRing(active: active, color: const Color(0xFFB8860B), icon: Icons.warning_amber),
          ),
          const SizedBox(height: 12),
          _InfoCard(
            icon: Icons.alt_route_outlined, baseColor: signalTeal,
            title: 'Plan a route',
            subtitle: 'Fastest vs. safer route',
            description: 'Compare the fastest route against a safer one that avoids high-risk zones and '
                'active incidents.',
            onTap: () => widget.onNavigate(5),
            illustrationBuilder: (active) => _MiniMapIllustration(active: active),
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
            illustrationBuilder: (active) => _ChatBubbleIllustration(active: active, color: steelBlue),
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

/// Generic looping-animation driver: starts repeating only while [active]
/// (hover) is true, stops otherwise, so idle cards never burn a frame.
/// Every illustration below is built from this one ticker instead of each
/// wiring its own AnimationController.
class _HoverAnim extends StatefulWidget {
  final bool active;
  final Duration duration;
  final Widget Function(BuildContext context, double t) builder;

  const _HoverAnim({required this.active, required this.builder, this.duration = const Duration(milliseconds: 1200)});

  @override
  State<_HoverAnim> createState() => _HoverAnimState();
}

class _HoverAnimState extends State<_HoverAnim> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: widget.duration);
    if (widget.active) _controller.repeat();
  }

  @override
  void didUpdateWidget(_HoverAnim old) {
    super.didUpdateWidget(old);
    if (widget.active && !_controller.isAnimating) {
      _controller.repeat();
    } else if (!widget.active && _controller.isAnimating) {
      _controller.stop();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(animation: _controller, builder: (context, _) => widget.builder(context, _controller.value));
  }
}

/// A ring that expands and fades around a static icon, looping -- used
/// for Check your flood risk (location "ping"), Report a flood (shutter
/// pulse), and Check alerts (warning pulse).
class _PulseRing extends StatelessWidget {
  final bool active;
  final Color color;
  final IconData icon;
  static const box = 60.0;
  static const iconSize = 26.0;
  const _PulseRing({required this.active, required this.color, required this.icon});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: box,
      child: Center(
        child: _HoverAnim(
          active: active,
          duration: const Duration(milliseconds: 1300),
          builder: (context, t) => SizedBox(
            width: box, height: box,
            child: Stack(alignment: Alignment.center, children: [
              Container(
                width: box * (0.55 + t * 0.6), height: box * (0.55 + t * 0.6),
                decoration: BoxDecoration(shape: BoxShape.circle, color: color.withValues(alpha: (1 - t) * 0.3)),
              ),
              Icon(icon, size: iconSize, color: color),
            ]),
          ),
        ),
      ),
    );
  }
}

/// A real chat-bubble shape (not just loose dots) with 3 bouncing dots
/// inside, for Ask the AI Assistant -- sized and shaped to actually read
/// as "a chat UI" on a full-width card, rather than a small decoration
/// floating in empty space.
class _ChatBubbleIllustration extends StatelessWidget {
  final bool active;
  final Color color;
  const _ChatBubbleIllustration({required this.active, required this.color});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 52,
      child: Align(
        alignment: Alignment.centerLeft,
        child: _HoverAnim(
          active: active,
          duration: const Duration(milliseconds: 900),
          builder: (context, t) => Container(
            width: 170, height: 46,
            padding: const EdgeInsets.symmetric(horizontal: 18),
            decoration: BoxDecoration(
              color: tintBackground(context, color),
              borderRadius: BorderRadius.circular(23),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(3, (i) {
                final phase = (t - i * 0.2) % 1.0;
                final bounce = phase < 0.5 ? phase * 2 : 2 - phase * 2;
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 5),
                  child: Transform.translate(
                    offset: Offset(0, -bounce.clamp(0.0, 1.0) * 8),
                    child: Container(width: 10, height: 10, decoration: BoxDecoration(shape: BoxShape.circle, color: color)),
                  ),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }
}

/// A skyline silhouette with a location pin and expanding radar-style
/// ripple rings above it -- a "scanning this area" visual for Check your
/// flood risk, sized to fill a full-width card rather than one small
/// centered icon.
class _ZoneScanIllustration extends StatelessWidget {
  final bool active;
  const _ZoneScanIllustration({required this.active});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 56,
      width: double.infinity,
      child: _HoverAnim(
        active: active,
        duration: const Duration(milliseconds: 1600),
        builder: (context, t) => CustomPaint(
          painter: _ZoneScanPainter(progress: t),
          size: const Size(double.infinity, 56),
        ),
      ),
    );
  }
}

class _ZoneScanPainter extends CustomPainter {
  final double progress;
  _ZoneScanPainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;

    final buildingPaint = Paint()..color = const Color(0xFFCBD5DC);
    final buildings = [
      Rect.fromLTWH(w * 0.03, h * 0.55, w * 0.09, h * 0.45),
      Rect.fromLTWH(w * 0.15, h * 0.35, w * 0.08, h * 0.65),
      Rect.fromLTWH(w * 0.26, h * 0.5, w * 0.07, h * 0.5),
      Rect.fromLTWH(w * 0.63, h * 0.42, w * 0.08, h * 0.58),
      Rect.fromLTWH(w * 0.74, h * 0.58, w * 0.09, h * 0.42),
      Rect.fromLTWH(w * 0.86, h * 0.48, w * 0.07, h * 0.52),
    ];
    for (final b in buildings) {
      canvas.drawRect(b, buildingPaint);
    }
    canvas.drawRect(Rect.fromLTWH(0, h - 3, w, 3), Paint()..color = const Color(0xFFDDE4E9));

    final pinX = w * 0.45, pinY = h * 0.42;
    for (int i = 0; i < 2; i++) {
      final ringT = (progress + i * 0.5) % 1.0;
      final radius = 7 + ringT * 24;
      canvas.drawCircle(
        Offset(pinX, pinY), radius,
        Paint()
          ..color = signalTeal.withValues(alpha: (1 - ringT) * 0.35)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.2,
      );
    }
    canvas.drawCircle(Offset(pinX, pinY), 6, Paint()..color = signalTeal);
    canvas.drawCircle(Offset(pinX, pinY), 6, Paint()..color = Colors.white..style = PaintingStyle.stroke..strokeWidth = 1.3);
  }

  @override
  bool shouldRepaint(covariant _ZoneScanPainter oldDelegate) => oldDelegate.progress != progress;
}

/// A gentle rise-and-fall of 6 rain "bars" on a baseline (a miniature of
/// the real Rainfall screen's line chart), for Rainfall forecast. Sized
/// to match the other full-width-card illustrations (~56px tall).
class _RainfallBars extends StatelessWidget {
  final bool active;
  const _RainfallBars({required this.active});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 56,
      child: _HoverAnim(
        active: active,
        duration: const Duration(milliseconds: 1100),
        builder: (context, t) => Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Expanded(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: List.generate(6, (i) {
                  final phase = (t - i * 0.12) % 1.0;
                  final h = 8 + (phase < 0.5 ? phase * 2 : 2 - phase * 2) * 34;
                  return Container(
                    width: 7, height: h, margin: const EdgeInsets.symmetric(horizontal: 3),
                    decoration: BoxDecoration(color: signalTeal, borderRadius: BorderRadius.circular(3)),
                  );
                }),
              ),
            ),
            Container(height: 3, color: const Color(0xFFDDE4E9)),
          ],
        ),
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

/// A small decorative "map" -- two abstract winding routes between a
/// from/to pin, in the same orange/teal/green/navy tokens the real
/// Routing screen uses, with a small dot animating along the safer
/// (teal) path while hovered. Hand-drawn via CustomPainter rather than a
/// real map tile or image asset: this is a hover decoration, not a real
/// map, and shouldn't imply more precision than that.
class _MiniMapIllustration extends StatelessWidget {
  final bool active;
  const _MiniMapIllustration({required this.active});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 56,
      width: double.infinity,
      child: _HoverAnim(
        active: active,
        duration: const Duration(milliseconds: 1600),
        builder: (context, t) => CustomPaint(
          painter: _MiniMapPainter(progress: t),
          size: const Size(double.infinity, 56),
        ),
      ),
    );
  }
}

class _MiniMapPainter extends CustomPainter {
  final double progress;
  _MiniMapPainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final fastPaint = Paint()..color = const Color(0xFFC1621B)..strokeWidth = 3..style = PaintingStyle.stroke..strokeCap = StrokeCap.round;
    final safePaint = Paint()..color = const Color(0xFF1B7A9E)..strokeWidth = 3..style = PaintingStyle.stroke..strokeCap = StrokeCap.round;

    final fastPath = Path()
      ..moveTo(w * 0.05, h * 0.78)
      ..cubicTo(w * 0.35, h * 0.92, w * 0.5, h * 0.52, w * 0.95, h * 0.15);
    final safePath = Path()
      ..moveTo(w * 0.05, h * 0.78)
      ..cubicTo(w * 0.3, h * 0.3, w * 0.65, h * 0.88, w * 0.95, h * 0.15);

    canvas.drawPath(safePath, safePaint);
    canvas.drawPath(fastPath, fastPaint);

    final fromPaint = Paint()..color = const Color(0xFF1E8A4C);
    final toPaint = Paint()..color = const Color(0xFF0B2545);
    canvas.drawCircle(Offset(w * 0.05, h * 0.78), 5, fromPaint);
    canvas.drawCircle(Offset(w * 0.95, h * 0.15), 5, toPaint);

    final metrics = safePath.computeMetrics().toList();
    if (metrics.isNotEmpty) {
      final metric = metrics.first;
      final tangent = metric.getTangentForOffset(metric.length * progress);
      if (tangent != null) {
        canvas.drawCircle(tangent.position, 5.2, Paint()..color = const Color(0xFF1B7A9E));
        canvas.drawCircle(tangent.position, 5.2, Paint()..color = Colors.white..style = PaintingStyle.stroke..strokeWidth = 1.4);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _MiniMapPainter oldDelegate) => oldDelegate.progress != progress;
}
