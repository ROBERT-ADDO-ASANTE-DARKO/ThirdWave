// theme.dart — the ThirdWave brand tokens (Spec Section 8.1, same ones
// streamlit_app/data_loader.py defines as INK_NAVY/STEEL_BLUE/SIGNAL_TEAL)
// built into an explicit Material 3 ColorScheme, rather than relying on
// colorSchemeSeed's auto-generated tones. One visual identity across the
// Streamlit console and this app, not two different-looking products.
//
// Layout/typography tokens (Manrope, rounded 13px inputs/buttons, 18px
// cards with a soft navy-tinted shadow, a filled rounded nav indicator)
// match the design concept Artifact (https://claude.ai/artifact/EzDdSKqK3D8CYQFCLFS9yh)
// -- set once here as theme defaults rather than per-widget overrides, so
// every TextField/Card/Button across all 7 screens picks it up for free.
//
// Dark theme: not just an inverted palette -- Ink Navy already reads as
// a "dark" color, so the dark theme keeps it as the chrome (app bar/nav)
// tier and adds two darker tiers below it (background, then card surface
// slightly lighter again for elevation contrast), rather than falling
// back to Material's default near-black. tintBackground()/tintForeground()
// below compute a theme-appropriate pale-tint-on-white (light) or dark-
// tint-on-navy (dark) pair from one saturated base hue, so every screen's
// risk/status colors (risk_colors.dart and the ad hoc banners in
// alert_screen.dart/report_screen.dart/rainfall_screen.dart) adapt to
// whichever theme is active without a second hardcoded hex table per
// color -- the thing that would otherwise make "add a dark theme" an
// ever-growing hand-tuned palette instead of one systematic rule.

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

const inkNavy = Color(0xFF0B2545);
const steelBlue = Color(0xFF1E4E6B);
const signalTeal = Color(0xFF1B7A9E);
const appBackground = Color(0xFFF3F6F8);
const _borderGrey = Color(0xFFE1E7EB);
const _outlineBorderGrey = Color(0xFFDAE2E8);

const _darkBackground = Color(0xFF0A1726);
const _darkSurface = Color(0xFF152B46);
const _darkChrome = Color(0xFF071220);
const _darkBorder = Color(0xFF24395A);

/// A theme-appropriate tinted background for a saturated base hue (e.g.
/// one of risk_colors.dart's LEVEL_COLOR tokens) -- pale-on-white in
/// light mode, dark-and-desaturated-on-navy in dark mode. Pair with
/// [tintForeground] for the matching readable text color.
Color tintBackground(BuildContext context, Color base) {
  final theme = Theme.of(context);
  final surface = theme.cardTheme.color ?? theme.colorScheme.surface;
  return Color.lerp(surface, base, 0.16)!;
}

/// The readable-text counterpart to [tintBackground]: a darker shade of
/// `base` in light mode, a lighter shade of `base` in dark mode.
Color tintForeground(BuildContext context, Color base) {
  final isDark = Theme.of(context).brightness == Brightness.dark;
  return Color.lerp(base, isDark ? Colors.white : Colors.black, 0.32)!;
}

ThemeData _buildTheme({required Brightness brightness}) {
  final isDark = brightness == Brightness.dark;
  final chrome = isDark ? _darkChrome : inkNavy;
  final background = isDark ? _darkBackground : appBackground;
  final surface = isDark ? _darkSurface : Colors.white;
  final border = isDark ? _darkBorder : _borderGrey;
  final outlineBorder = isDark ? _darkBorder : _outlineBorderGrey;
  final onSurface = isDark ? Colors.white : inkNavy;
  final baseTextTheme = isDark ? ThemeData.dark().textTheme : ThemeData.light().textTheme;

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    textTheme: GoogleFonts.manropeTextTheme(baseTextTheme),
    colorScheme: ColorScheme.fromSeed(
      seedColor: signalTeal,
      brightness: brightness,
    ).copyWith(
      primary: signalTeal,
      secondary: steelBlue,
      surfaceTint: signalTeal,
      surface: surface,
    ),
    scaffoldBackgroundColor: background,
    appBarTheme: AppBarTheme(
      backgroundColor: chrome,
      foregroundColor: Colors.white,
      centerTitle: false,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: chrome,
      indicatorColor: signalTeal,
      indicatorShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
      iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
            color: states.contains(WidgetState.selected) ? Colors.white : Colors.white70,
          )),
      labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
            color: states.contains(WidgetState.selected) ? Colors.white : Colors.white70,
            fontSize: 12,
          )),
    ),
    cardTheme: CardThemeData(
      elevation: 1,
      shadowColor: isDark ? Colors.black.withValues(alpha: 0.4) : inkNavy.withValues(alpha: 0.10),
      color: surface,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(13), borderSide: BorderSide(color: border, width: 1.5)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(13), borderSide: BorderSide(color: border, width: 1.5)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(13), borderSide: const BorderSide(color: signalTeal, width: 1.5)),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: signalTeal,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: onSurface,
        side: BorderSide(color: outlineBorder, width: 1.5),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        backgroundColor: WidgetStateProperty.resolveWith((states) =>
            states.contains(WidgetState.selected) ? signalTeal : null),
        foregroundColor: WidgetStateProperty.resolveWith((states) =>
            states.contains(WidgetState.selected) ? Colors.white : null),
      ),
    ),
  );
}

final ThemeData citizenAppTheme = _buildTheme(brightness: Brightness.light);
final ThemeData citizenAppDarkTheme = _buildTheme(brightness: Brightness.dark);
