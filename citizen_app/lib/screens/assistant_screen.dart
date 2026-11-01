// assistant_screen.dart — Phase 4 feature #6, AI Assistant. Mirrors
// streamlit_app/features/ai_assistant.py: a Claude tool-calling chat that
// only ever looks up data already computed elsewhere in this project
// (POST /assistant/chat, backed by backend/ai_tools.py + claude_chat.py).
//
// Stateless backend, same as every other call this app makes -- this
// screen owns the full conversation history and sends it whole on every
// turn (OpenAI-style chat shape), rather than the backend keeping a
// session the client would have to remember to clean up.
//
// Interface redesign: Claude/ChatGPT-style layout (avatar + flowing
// content, no chat bubbles), markdown rendering for assistant replies
// (gpt_markdown -- the model's system prompt in ai_tools.py already
// writes in markdown; previously this just dumped the raw "**bold**"
// text), a copy-to-clipboard action per assistant reply, and a glossary
// of the technical terms (SAR, composite score, assembly, ...) the
// assistant's answers actually use, reachable from the app bar before a
// citizen needs it.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:gpt_markdown_lite/gpt_markdown_lite.dart';

import '../services/api_client.dart';
import '../theme.dart';
import '../widgets/citizen_app_bar.dart';

class _ChatMessage {
  final String role; // "user" | "assistant"
  final String content;
  final List<Map<String, dynamic>>? toolLog;
  _ChatMessage({required this.role, required this.content, this.toolLog});
}

const _exampleQuestions = [
  "What's the flood risk near Kwame Nkrumah Circle?",
  'Which zones should get drain maintenance priority?',
  'How many people live in high-risk zones?',
  'What historical flood events have happened here?',
  'Compare the pilot assemblies by vulnerability score.',
];

// Terms the assistant's answers actually use (see ai_tools.py's
// SYSTEM_PROMPT and tool outputs) that a regular citizen likely hasn't
// seen before.
const _glossary = [
  (
    'Composite / vulnerability score',
    "A single 0-100 number for a zone that blends several satellite and terrain layers into one flood-risk "
        "estimate -- the main number the assistant cites.",
  ),
  (
    'SAR (radar water history)',
    "Synthetic Aperture Radar -- a satellite (Sentinel-1) that detects standing water on the ground, even "
        "through cloud cover. Historical SAR water-occurrence is one input to the score.",
  ),
  (
    'DEM (elevation)',
    "Digital Elevation Model -- a map of ground height (Copernicus DEM) used to find low-lying terrain where "
        "water naturally collects.",
  ),
  (
    'Land cover',
    "What's physically on the ground (built-up, bare soil, vegetation, water), from the ESA WorldCover "
        "satellite dataset.",
  ),
  (
    'Zone ID (e.g. RZ-042)',
    "An internal grid-cell label the risk engine uses for a small area of the pilot district.",
  ),
  (
    'Assembly',
    "Ghana's term for a local government district (e.g. Weija Gbawe Municipal) -- the administrative area a "
        "zone falls within.",
  ),
  (
    'Contributing factors',
    "The specific signals (e.g. 'near a waterway', 'low elevation') that pushed a particular zone's score up.",
  ),
  (
    'Verified citizen report',
    "A flood report submitted in this app that a local official has reviewed and confirmed -- shown as live "
        "evidence alongside the computed score, not a replacement for it.",
  ),
];

class AssistantScreen extends StatefulWidget {
  final ApiClient apiClient;
  const AssistantScreen({super.key, required this.apiClient});

  @override
  State<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends State<AssistantScreen> {
  final _inputController = TextEditingController();
  final _scrollController = ScrollController();
  final List<_ChatMessage> _messages = [];
  bool _sending = false;
  String? _error;

  Future<void> _send([String? text]) async {
    final message = (text ?? _inputController.text).trim();
    if (message.isEmpty || _sending) return;
    setState(() {
      _messages.add(_ChatMessage(role: 'user', content: message));
      _inputController.clear();
      _sending = true;
      _error = null;
    });
    _scrollToBottom();

    try {
      final resp = await widget.apiClient.postJson('/assistant/chat', {
        'messages': _messages.map((m) => {'role': m.role, 'content': m.content}).toList(),
      });
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      if (body['error'] != null) {
        setState(() => _error = body['error'] as String);
        return;
      }
      setState(() {
        _messages.add(_ChatMessage(
          role: 'assistant',
          content: body['reply'] as String? ?? '',
          toolLog: (body['tool_log'] as List?)?.cast<Map<String, dynamic>>(),
        ));
      });
    } catch (e) {
      setState(() => _error = 'Could not reach backend: $e');
    } finally {
      setState(() => _sending = false);
      _scrollToBottom();
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200), curve: Curves.easeOut,
        );
      }
    });
  }

  void _showGlossary() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (context) => DraggableScrollableSheet(
        initialChildSize: 0.65,
        minChildSize: 0.4,
        maxChildSize: 0.9,
        expand: false,
        builder: (context, scrollController) => ListView(
          controller: scrollController,
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
          children: [
            Center(
              child: Container(
                width: 40, height: 4,
                decoration: BoxDecoration(color: Colors.grey.withValues(alpha: 0.4), borderRadius: BorderRadius.circular(2)),
              ),
            ),
            const SizedBox(height: 16),
            Text('Terms the assistant uses', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(
              'A quick glossary for the technical terms you might see in an answer below.',
              style: TextStyle(color: Colors.grey[600], fontSize: 13),
            ),
            const SizedBox(height: 16),
            for (final (term, definition) in _glossary)
              Padding(
                padding: const EdgeInsets.only(bottom: 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(term, style: const TextStyle(fontWeight: FontWeight.bold, color: steelBlue)),
                    const SizedBox(height: 3),
                    Text(definition, style: const TextStyle(fontSize: 13, height: 1.35)),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: CitizenAppBar(
        eyebrow: 'Assistant',
        title: 'AI Assistant',
        actions: [
          IconButton(
            tooltip: 'Glossary of terms',
            icon: const Icon(Icons.menu_book_outlined, color: Colors.white),
            onPressed: _showGlossary,
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: _messages.isEmpty
                ? _EmptyState(onExample: _send, onGlossary: _showGlossary)
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    itemCount: _messages.length,
                    itemBuilder: (context, i) => _MessageRow(message: _messages[i]),
                  ),
          ),
          if (_sending)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 4),
              child: Center(child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(_error!, style: const TextStyle(color: Colors.red)),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 14),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Row(children: [
                  Expanded(
                    child: TextField(
                      controller: _inputController,
                      decoration: const InputDecoration(hintText: 'Ask about flood risk in the pilot district...'),
                      onSubmitted: (_) => _send(),
                      textInputAction: TextInputAction.send,
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _sending ? null : () => _send(),
                    icon: const Icon(Icons.arrow_upward),
                  ),
                ]),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// The gradient "sparkle" avatar every assistant message and the empty
// state's header use -- the "cool icon" asked for, distinguishing the AI
// from a plain chat contact.
class _AssistantAvatar extends StatelessWidget {
  final double size;
  const _AssistantAvatar({this.size = 32});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size, height: size,
      decoration: const BoxDecoration(
        gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [steelBlue, signalTeal]),
        shape: BoxShape.circle,
      ),
      child: Icon(Icons.auto_awesome, color: Colors.white, size: size * 0.55),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final void Function(String) onExample;
  final VoidCallback onGlossary;
  const _EmptyState({required this.onExample, required this.onGlossary});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
      children: [
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Column(
              children: [
                const _AssistantAvatar(size: 56),
                const SizedBox(height: 14),
                Text('Ask the AI Assistant', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 8),
                Text(
                  'Ask questions about flood vulnerability in the pilot district. Answers are grounded in data '
                  "already computed by the risk engine, plus live verified citizen reports -- this chat looks "
                  "things up, it doesn't run new geospatial analysis or fetch live satellite imagery.",
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey[600], fontSize: 13),
                ),
                const SizedBox(height: 10),
                TextButton.icon(
                  onPressed: onGlossary,
                  icon: const Icon(Icons.menu_book_outlined, size: 16),
                  label: const Text('See what SAR, composite score, etc. mean'),
                ),
                const SizedBox(height: 18),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text('Try asking', style: Theme.of(context).textTheme.labelLarge),
                ),
                const SizedBox(height: 8),
                ..._exampleQuestions.map((q) => Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: OutlinedButton(
                        style: OutlinedButton.styleFrom(
                          alignment: Alignment.centerLeft,
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                        ),
                        onPressed: () => onExample(q),
                        child: Text(q),
                      ),
                    )),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _MessageRow extends StatelessWidget {
  final _ChatMessage message;
  const _MessageRow({required this.message});

  void _copy(BuildContext context) {
    Clipboard.setData(ClipboardData(text: message.content));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Copied to clipboard'), duration: Duration(seconds: 1)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    final textColor = Theme.of(context).textTheme.bodyMedium?.color;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              isUser
                  ? CircleAvatar(
                      radius: 16,
                      backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                      child: Icon(Icons.person_outline, size: 18, color: textColor),
                    )
                  : const _AssistantAvatar(),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(isUser ? 'You' : 'ThirdWave Assistant',
                        style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12, color: Colors.grey[600])),
                    const SizedBox(height: 4),
                    isUser
                        ? Text(message.content, style: TextStyle(color: textColor))
                        : GptMarkdown(message.content, style: TextStyle(color: textColor)),
                    if (message.toolLog != null && message.toolLog!.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Theme(
                        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                        child: ExpansionTile(
                          tilePadding: EdgeInsets.zero,
                          title: Row(mainAxisSize: MainAxisSize.min, children: [
                            Icon(Icons.build_outlined, size: 13, color: Colors.grey[600]),
                            const SizedBox(width: 5),
                            Text('${message.toolLog!.length} tool call(s) used',
                                style: TextStyle(fontSize: 11, color: Colors.grey[600])),
                          ]),
                          children: message.toolLog!.map((call) => Padding(
                                padding: const EdgeInsets.only(bottom: 6),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text('${call['tool']}(${jsonEncode(call['input'])})',
                                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: textColor)),
                                    Text(jsonEncode(call['result']),
                                        style: TextStyle(fontSize: 10, color: Colors.grey[600])),
                                  ],
                                ),
                              )).toList(),
                        ),
                      ),
                    ],
                    if (!isUser) ...[
                      const SizedBox(height: 2),
                      InkWell(
                        onTap: () => _copy(context),
                        borderRadius: BorderRadius.circular(6),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 2),
                          child: Row(mainAxisSize: MainAxisSize.min, children: [
                            Icon(Icons.copy_outlined, size: 14, color: Colors.grey[600]),
                            const SizedBox(width: 5),
                            Text('Copy', style: TextStyle(fontSize: 12, color: Colors.grey[600])),
                          ]),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
