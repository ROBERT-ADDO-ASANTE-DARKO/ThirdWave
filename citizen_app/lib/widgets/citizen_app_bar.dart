// citizen_app_bar.dart — the Artifact's `.topbar` pattern (a small
// uppercase eyebrow label over a bold title, on Ink Navy) as a real
// AppBar, so every screen still gets AppBar's usual behavior (back
// button, actions, safe-area handling) for free via appBarTheme in
// theme.dart -- this only customizes the title content.

import 'package:flutter/material.dart';

class CitizenAppBar extends StatelessWidget implements PreferredSizeWidget {
  final String eyebrow;
  final String title;
  final List<Widget>? actions;

  const CitizenAppBar({super.key, required this.eyebrow, required this.title, this.actions});

  @override
  Size get preferredSize => const Size.fromHeight(72);

  @override
  Widget build(BuildContext context) {
    return AppBar(
      toolbarHeight: 72,
      titleSpacing: 20,
      actions: actions,
      title: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            eyebrow.toUpperCase(),
            style: const TextStyle(
              fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 1.0, color: Color(0xFF7FA7BE),
            ),
          ),
          const SizedBox(height: 2),
          Text(title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: Colors.white)),
        ],
      ),
    );
  }
}
