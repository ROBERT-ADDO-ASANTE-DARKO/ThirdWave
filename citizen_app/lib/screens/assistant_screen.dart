// assistant_screen.dart — Phase 4 feature #6, AI Assistant. Mirrors
// streamlit_app/features/ai_assistant.py: a Claude tool-calling chat that
// only ever looks up data already computed elsewhere in this project
// (POST /assistant/chat, backed by backend/ai_tools.py + claude_chat.py).
//
// Stateless backend, same as every other call this app makes -- this
// screen owns the full conversation history and sends it whole on every
// turn (OpenAI-style chat shape), rather than the backend keeping a
// session the client would have to remember to clean up.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../services/api_client.dart';

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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AI Assistant')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: Text(
              'Ask questions about flood vulnerability in the pilot district. Answers are grounded in data '
              'already computed by the risk engine, plus live verified citizen reports -- this chat looks '
              "things up, it doesn't run new geospatial analysis or fetch live satellite imagery.",
              style: const TextStyle(color: Colors.grey, fontSize: 12),
            ),
          ),
          if (_messages.isEmpty)
            Padding(
              padding: const EdgeInsets.all(16),
              child: ExpansionTile(
                title: const Text('Example questions'),
                tilePadding: EdgeInsets.zero,
                children: _exampleQuestions.map((q) => ListTile(
                  dense: true,
                  title: Text(q),
                  onTap: () => _send(q),
                )).toList(),
              ),
            ),
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (context, i) => _MessageBubble(message: _messages[i]),
            ),
          ),
          if (_sending) const Padding(
            padding: EdgeInsets.symmetric(vertical: 4),
            child: Center(child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))),
          ),
          if (_error != null) Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text(_error!, style: const TextStyle(color: Colors.red)),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(children: [
              Expanded(child: TextField(
                controller: _inputController,
                decoration: const InputDecoration(hintText: 'Ask about flood risk in the pilot district...'),
                onSubmitted: (_) => _send(),
              )),
              const SizedBox(width: 8),
              IconButton.filled(onPressed: _sending ? null : () => _send(), icon: const Icon(Icons.send)),
            ]),
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  final _ChatMessage message;
  const _MessageBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.8),
        decoration: BoxDecoration(
          color: isUser ? const Color(0xFF1B7A9E) : const Color(0xFFEDEDED),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(message.content, style: TextStyle(color: isUser ? Colors.white : Colors.black87)),
            if (message.toolLog != null && message.toolLog!.isNotEmpty) ...[
              const SizedBox(height: 6),
              Theme(
                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: Text('🔧 ${message.toolLog!.length} tool call(s) used',
                      style: const TextStyle(fontSize: 11, color: Colors.black54)),
                  children: message.toolLog!.map((call) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${call['tool']}(${jsonEncode(call['input'])})',
                            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                        Text(jsonEncode(call['result']), style: const TextStyle(fontSize: 10, color: Colors.black54)),
                      ],
                    ),
                  )).toList(),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
