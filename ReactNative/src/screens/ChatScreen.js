import React, { useState, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, StyleSheet,
} from 'react-native';
import { chatAsk } from '../api';

export default function ChatScreen() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const listRef = useRef(null);

  const send = async () => {
    const question = input.trim();
    if (!question || loading) return;

    const userMsg = { id: Date.now(), role: 'user', text: question };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const data = await chatAsk(question);
      const botMsg = {
        id: Date.now() + 1,
        role: 'bot',
        text: data.answer || data.error || 'Sin respuesta.',
        sources: data.sources || [],
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id: Date.now() + 1, role: 'bot', text: '⚠️ No se pudo contactar al asistente.' },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
    }
  };

  const renderItem = ({ item }) => (
    <View style={[styles.bubble, item.role === 'user' ? styles.userBubble : styles.botBubble]}>
      <Text style={item.role === 'user' ? styles.userText : styles.botText}>
        {item.text}
      </Text>
      {item.sources?.length > 0 && (
        <Text style={styles.sources}>
          📎 {item.sources.map((s) => s.label).join(', ')}
        </Text>
      )}
    </View>
  );

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderItem}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <Text style={styles.empty}>
            Pregunta por stock, movimientos, sensores o alertas de ICChocolate.
          </Text>
        }
      />
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Escribe tu pregunta…"
          placeholderTextColor="#999"
          editable={!loading}
          onSubmitEditing={send}
          returnKeyType="send"
        />
        <TouchableOpacity
          style={[styles.sendBtn, loading && { opacity: 0.5 }]}
          onPress={send}
          disabled={loading}
        >
          <Text style={styles.sendText}>{loading ? '…' : '➤'}</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fdf6ec' },
  list: { padding: 12, paddingBottom: 8 },
  empty: { textAlign: 'center', color: '#999', marginTop: 60, paddingHorizontal: 30 },
  bubble: { marginBottom: 8, padding: 12, borderRadius: 12, maxWidth: '85%' },
  userBubble: { backgroundColor: '#4a2c2a', alignSelf: 'flex-end' },
  botBubble: { backgroundColor: '#fff', alignSelf: 'flex-start', elevation: 1 },
  userText: { color: '#fff', fontSize: 15 },
  botText: { color: '#333', fontSize: 15 },
  sources: { fontSize: 11, color: '#8b6f5e', marginTop: 6 },
  inputRow: {
    flexDirection: 'row', padding: 8, borderTopWidth: 1, borderColor: '#e0d5c4',
    backgroundColor: '#fff',
  },
  input: {
    flex: 1, borderWidth: 1, borderColor: '#d4c4a8', borderRadius: 20,
    paddingHorizontal: 14, paddingVertical: 8, fontSize: 15, backgroundColor: '#fdf6ec',
  },
  sendBtn: {
    marginLeft: 8, backgroundColor: '#4a2c2a', width: 44, height: 44,
    borderRadius: 22, alignItems: 'center', justifyContent: 'center',
  },
  sendText: { color: '#fff', fontSize: 18 },
});

