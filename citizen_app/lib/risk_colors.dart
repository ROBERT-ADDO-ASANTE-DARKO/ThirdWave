// risk_colors.dart — badge colors for the Low/Moderate/High/Very High
// risk levels, matching the design concept Artifact
// (https://claude.ai/artifact/EzDdSKqK3D8CYQFCLFS9yh): a light tint of
// the level's color with a darker, readable shade of the same hue for
// text -- not solid LEVEL_COLOR-on-white, which the Artifact's
// accessibility pass flagged as failing contrast at small sizes for the
// amber/moderate tier in particular.
//
// Same 4 base hues as streamlit_app/data_loader.py's LEVEL_COLOR (Low
// #1E8A4C, Moderate #B8860B, High #C1621B, Very High #B0241D). The
// bg/text pair is now computed via theme.dart's tintBackground()/
// tintForeground() from those hues rather than a separate hardcoded
// table, so it adapts to the active light/dark theme automatically.

import 'package:flutter/material.dart';

import 'theme.dart';

const Map<String, Color> riskBaseColor = {
  'Low': Color(0xFF1E8A4C),
  'Moderate': Color(0xFFB8860B),
  'High': Color(0xFFC1621B),
  'Very High': Color(0xFFB0241D),
};

const Color _unknownBase = Color(0xFF6B7280);

class RiskBadgeColors {
  final Color background;
  final Color text;
  const RiskBadgeColors(this.background, this.text);
}

RiskBadgeColors riskBadgeFor(BuildContext context, String level) {
  final base = riskBaseColor[level] ?? _unknownBase;
  return RiskBadgeColors(tintBackground(context, base), tintForeground(context, base));
}

/// A plain-language headline for a channel_encroachment result's level --
/// leads with what it actually means before the technical term gets
/// introduced in the sentence underneath, rather than opening with
/// "Channel encroachment: Very High" as a jargon-first bold headline.
/// Shared between My Zone and Alert, which both display this field.
String channelEncroachmentHeadline(Map<String, dynamic> encroachment) {
  final level = encroachment['level'] as String? ?? '';
  switch (level) {
    case 'Very High':
    case 'High':
      return 'Buildings here are built very close to a drainage channel';
    case 'Moderate':
      return 'Some buildings here are fairly close to a drainage channel';
    default:
      return 'Buildings here sit a safer distance from any mapped drainage channel';
  }
}
