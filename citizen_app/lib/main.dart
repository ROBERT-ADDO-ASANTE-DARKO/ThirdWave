// main.dart — citizen app shell: identity + push registration at
// startup, then a bottom-nav holding Home (shell status) plus the six
// citizen features from streamlit_app's README table. All six are now
// real screens -- see MOBILE_APP_PHASES.md's Phase 4 checklist.

import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';

import 'screens/address_vulnerability_screen.dart';
import 'screens/alert_screen.dart';
import 'screens/assistant_screen.dart';
import 'screens/home_screen.dart';
import 'screens/rainfall_screen.dart';
import 'screens/report_screen.dart';
import 'screens/routing_screen.dart';
import 'services/api_client.dart';
import 'services/identity_service.dart';
import 'services/push_service.dart';
import 'services/theme_controller.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final apiClient = ApiClient();
  final reporterRef = await IdentityService().getOrCreateReporterRef();
  final pushService = PushService(apiClient);
  await pushService.init();
  if (pushService.status == PushStatus.tokenObtained) {
    await pushService.registerWithBackend();
  }
  final themeController = ThemeController();
  await themeController.load();

  runApp(CitizenApp(
    reporterRef: reporterRef, pushService: pushService, apiClient: apiClient,
    themeController: themeController,
  ));
}

class CitizenApp extends StatelessWidget {
  final String reporterRef;
  final PushService pushService;
  final ApiClient apiClient;
  final ThemeController themeController;

  const CitizenApp({
    super.key,
    required this.reporterRef,
    required this.pushService,
    required this.apiClient,
    required this.themeController,
  });

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: themeController,
      builder: (context, _) => MaterialApp(
        title: 'ThirdWave Citizen',
        theme: citizenAppTheme,
        darkTheme: citizenAppDarkTheme,
        themeMode: themeController.mode,
        home: _NavShell(
          reporterRef: reporterRef, pushService: pushService, apiClient: apiClient,
          themeController: themeController,
        ),
      ),
    );
  }
}

class _NavShell extends StatefulWidget {
  final String reporterRef;
  final PushService pushService;
  final ApiClient apiClient;
  final ThemeController themeController;

  const _NavShell({
    required this.reporterRef, required this.pushService, required this.apiClient,
    required this.themeController,
  });

  @override
  State<_NavShell> createState() => _NavShellState();
}

class _NavShellState extends State<_NavShell> {
  int _index = 0;

  // Built once, not per build() -- each screen's State (My Zone's last
  // search, a half-typed Report draft, Tide's conversation, an in-progress
  // Routing navigation session) must survive switching tabs and back.
  // IndexedStack keeps every screen mounted and just swaps which one is
  // painted; rebuilding this list on every setState (the previous
  // approach) created a fresh widget -- and fresh State -- per tab switch,
  // which silently reset all seven screens every time, not just the one
  // a citizen happened to notice it on.
  late final List<Widget> _screens = [
    HomeScreen(
      reporterRef: widget.reporterRef, pushService: widget.pushService, apiClient: widget.apiClient,
      onNavigate: _goTo, themeController: widget.themeController,
    ),
    AddressVulnerabilityScreen(apiClient: widget.apiClient, pushService: widget.pushService),
    ReportScreen(apiClient: widget.apiClient, reporterRef: widget.reporterRef, pushService: widget.pushService),
    RainfallScreen(apiClient: widget.apiClient),
    AlertScreen(apiClient: widget.apiClient, pushService: widget.pushService),
    RoutingScreen(apiClient: widget.apiClient, pushService: widget.pushService),
    AssistantScreen(apiClient: widget.apiClient),
  ];

  void _goTo(int index) => setState(() => _index = index);

  // Surfaces a foreground FCM push (officer-verified incident near this
  // device, see backend/push.py's notify_nearby_devices) as a real in-app
  // banner regardless of which tab is active -- previously this only fed
  // a debug-style list buried in Home's "Connection & notifications"
  // panel, which stays as a diagnostic log; this is the actual
  // user-facing notification. Background/closed-app delivery is
  // unchanged -- Android's system tray already handles that via FCM
  // without any app code.
  StreamSubscription<RemoteMessage>? _pushSub;

  @override
  void initState() {
    super.initState();
    _pushSub = widget.pushService.onForegroundMessage.listen(_showPushBanner);
  }

  @override
  void dispose() {
    _pushSub?.cancel();
    super.dispose();
  }

  void _showPushBanner(RemoteMessage message) {
    final title = message.notification?.title ?? 'ThirdWave Alert';
    final body = message.notification?.body;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        behavior: SnackBarBehavior.floating,
        duration: const Duration(seconds: 6),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Icon(Icons.notifications_active, color: Colors.white, size: 18),
              const SizedBox(width: 8),
              Expanded(child: Text(title, style: const TextStyle(fontWeight: FontWeight.bold))),
            ]),
            if (body != null && body.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(body),
            ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _screens),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: _goTo,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.place_outlined), selectedIcon: Icon(Icons.place), label: 'My Zone'),
          NavigationDestination(icon: Icon(Icons.camera_alt_outlined), selectedIcon: Icon(Icons.camera_alt), label: 'Report'),
          NavigationDestination(icon: Icon(Icons.water_drop_outlined), selectedIcon: Icon(Icons.water_drop), label: 'Rainfall'),
          NavigationDestination(icon: Icon(Icons.warning_amber_outlined), selectedIcon: Icon(Icons.warning), label: 'Alert'),
          NavigationDestination(icon: Icon(Icons.alt_route_outlined), selectedIcon: Icon(Icons.alt_route), label: 'Routing'),
          NavigationDestination(icon: Icon(Icons.chat_bubble_outline), selectedIcon: Icon(Icons.chat_bubble), label: 'Assistant'),
        ],
      ),
    );
  }
}
