// placeholder_screen.dart — shared "not built yet" screen for the five
// citizen features that haven't been implemented yet. Each gets replaced
// by its own screen file as it's built (see MOBILE_APP_PHASES.md's
// Phase 4 checklist); this keeps the nav shell honest about what's real.

import 'package:flutter/material.dart';

class PlaceholderScreen extends StatelessWidget {
  final String title;
  final String featureNote;

  const PlaceholderScreen({super.key, required this.title, required this.featureNote});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.construction, size: 48),
              const SizedBox(height: 16),
              Text('Not built yet', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(featureNote, textAlign: TextAlign.center),
            ],
          ),
        ),
      ),
    );
  }
}
