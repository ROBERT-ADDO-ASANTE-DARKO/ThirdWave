// address_autocomplete_field.dart — a drop-in replacement for the bare
// TextField every address-search field in this app used, adding
// suggestions backed by GET /geocode/suggest (backend/geo_data.py's
// suggest_places() -- curated local matches first, live Nominatim
// fallback). Debounced client-side (400ms after the last keystroke, only
// once text.length >= 2): Nominatim's usage policy explicitly prohibits
// firing a request per keystroke, so the actual throttling that matters
// lives here, not on the backend.
//
// Suggestions render inline, directly below the field as a plain Column
// of ListTiles, not a floating Overlay -- simpler, no positioning/z-index
// code, consistent with how this app already expands content in place
// elsewhere (Tide's example-questions list, Home's hover-reveal cards)
// rather than overlaying it.
//
// Tapping a suggestion fills the field and, only if the screen provided
// onSubmitted, immediately runs that screen's existing search -- the
// same callback typing-and-pressing-Enter already uses, so selecting a
// suggestion behaves like submitting rather than a separate path.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../services/api_client.dart';

class AddressAutocompleteField extends StatefulWidget {
  final TextEditingController controller;
  final ApiClient apiClient;
  final InputDecoration decoration;
  final ValueChanged<String>? onSubmitted;

  const AddressAutocompleteField({
    super.key,
    required this.controller,
    required this.apiClient,
    required this.decoration,
    this.onSubmitted,
  });

  @override
  State<AddressAutocompleteField> createState() => _AddressAutocompleteFieldState();
}

class _AddressAutocompleteFieldState extends State<AddressAutocompleteField> {
  Timer? _debounce;
  List<Map<String, dynamic>> _suggestions = [];

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _onChanged(String text) {
    _debounce?.cancel();
    if (text.trim().length < 2) {
      if (_suggestions.isNotEmpty) setState(() => _suggestions = []);
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 400), () => _fetchSuggestions(text));
  }

  Future<void> _fetchSuggestions(String text) async {
    try {
      final resp = await widget.apiClient.get('/geocode/suggest', query: {'q': text});
      if (!mounted || resp.statusCode != 200) return;
      final body = jsonDecode(resp.body) as List;
      setState(() => _suggestions = body.cast<Map<String, dynamic>>());
    } catch (_) {
      // Suggestions are a nicety, not the critical path -- the field and
      // its existing submit button still work regardless of this failing.
    }
  }

  void _select(Map<String, dynamic> suggestion) {
    final label = suggestion['label'] as String;
    widget.controller.text = label;
    setState(() => _suggestions = []);
    FocusScope.of(context).unfocus();
    widget.onSubmitted?.call(label);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          controller: widget.controller,
          decoration: widget.decoration,
          onChanged: _onChanged,
          onSubmitted: widget.onSubmitted,
        ),
        if (_suggestions.isNotEmpty)
          Card(
            margin: const EdgeInsets.only(top: 2),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: _suggestions.map((s) => ListTile(
                    dense: true,
                    leading: const Icon(Icons.place_outlined, size: 18),
                    title: Text(s['label'] as String, maxLines: 2, overflow: TextOverflow.ellipsis),
                    onTap: () => _select(s),
                  )).toList(),
            ),
          ),
      ],
    );
  }
}
