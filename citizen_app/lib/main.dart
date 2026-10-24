// main.dart — citizen app shell: identity + push registration at
// startup, then a bottom-nav holding Home (shell status) plus the six
// citizen features from streamlit_app's README table. Five of six are
// still PlaceholderScreen -- see MOBILE_APP_PHASES.md's Phase 4
// checklist for what's built vs. not.

import 'package:flutter/material.dart';

import 'screens/address_vulnerability_screen.dart';
import 'screens/home_screen.dart';
import 'screens/placeholder_screen.dart';
import 'screens/report_screen.dart';
import 'services/api_client.dart';
import 'services/identity_service.dart';
import 'services/push_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final apiClient = ApiClient();
  final reporterRef = await IdentityService().getOrCreateReporterRef();
  final pushService = PushService(apiClient);
  await pushService.init();
  if (pushService.status == PushStatus.tokenObtained) {
    await pushService.registerWithBackend();
  }

  runApp(CitizenApp(reporterRef: reporterRef, pushService: pushService, apiClient: apiClient));
}

class CitizenApp extends StatelessWidget {
  final String reporterRef;
  final PushService pushService;
  final ApiClient apiClient;

  const CitizenApp({
    super.key,
    required this.reporterRef,
    required this.pushService,
    required this.apiClient,
  });

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ThirdWave Citizen',
      theme: ThemeData(colorSchemeSeed: const Color(0xFF1B7A9E), useMaterial3: true),
      home: _NavShell(reporterRef: reporterRef, pushService: pushService, apiClient: apiClient),
    );
  }
}

class _NavShell extends StatefulWidget {
  final String reporterRef;
  final PushService pushService;
  final ApiClient apiClient;

  const _NavShell({required this.reporterRef, required this.pushService, required this.apiClient});

  @override
  State<_NavShell> createState() => _NavShellState();
}

class _NavShellState extends State<_NavShell> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final screens = [
      HomeScreen(reporterRef: widget.reporterRef, pushService: widget.pushService, apiClient: widget.apiClient),
      AddressVulnerabilityScreen(apiClient: widget.apiClient),
      ReportScreen(apiClient: widget.apiClient, reporterRef: widget.reporterRef),
      const PlaceholderScreen(
        title: 'Rainfall',
        featureNote: '6-hour precipitation outlook per zone.',
      ),
      const PlaceholderScreen(
        title: 'Alert',
        featureNote: 'High-Risk Zone Alert -- zone score + rainfall + nearby incidents.',
      ),
      const PlaceholderScreen(
        title: 'Routing',
        featureNote: 'Safer Routing -- fastest vs. vulnerability-weighted route.',
      ),
      const PlaceholderScreen(
        title: 'Assistant',
        featureNote: 'AI Assistant, same as the government console.',
      ),
    ];

    return Scaffold(
      body: screens[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.place), label: 'My Zone'),
          NavigationDestination(icon: Icon(Icons.camera_alt), label: 'Report'),
          NavigationDestination(icon: Icon(Icons.water_drop), label: 'Rainfall'),
          NavigationDestination(icon: Icon(Icons.warning), label: 'Alert'),
          NavigationDestination(icon: Icon(Icons.alt_route), label: 'Routing'),
          NavigationDestination(icon: Icon(Icons.chat), label: 'Assistant'),
        ],
      ),
    );
  }
}
