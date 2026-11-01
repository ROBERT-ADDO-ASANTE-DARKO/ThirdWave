// main.dart — citizen app shell: identity + push registration at
// startup, then a bottom-nav holding Home (shell status) plus the six
// citizen features from streamlit_app's README table. All six are now
// real screens -- see MOBILE_APP_PHASES.md's Phase 4 checklist.

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

  void _goTo(int index) => setState(() => _index = index);

  @override
  Widget build(BuildContext context) {
    final screens = [
      HomeScreen(
        reporterRef: widget.reporterRef, pushService: widget.pushService, apiClient: widget.apiClient,
        onNavigate: _goTo, themeController: widget.themeController,
      ),
      AddressVulnerabilityScreen(apiClient: widget.apiClient),
      ReportScreen(apiClient: widget.apiClient, reporterRef: widget.reporterRef),
      RainfallScreen(apiClient: widget.apiClient),
      AlertScreen(apiClient: widget.apiClient),
      RoutingScreen(apiClient: widget.apiClient),
      AssistantScreen(apiClient: widget.apiClient),
    ];

    return Scaffold(
      body: screens[_index],
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
