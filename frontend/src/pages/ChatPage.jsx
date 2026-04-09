import { useEffect, useState, useRef } from "react";
import { useAuth } from "../services/auth/useAuth";
import { useParams, useNavigate } from "react-router-dom";
import usePageTitle from "../components/layout/usePageTitle";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import toast from "react-hot-toast";

export default function ChatPage() {
  const { getMessages, sendMessage, createChat } = useAuth();
  const { org, agentId, chatId } = useParams();
  const navigate = useNavigate();

  const [title, setTitle] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showTypingBubble, setShowTypingBubble] = useState(false);

  const textareaRef = useRef(null);
  const bottomRef = useRef(null);

  usePageTitle(title || "New Chat");

  // Load messages
  useEffect(() => {
    if (!chatId) {
      setMessages([]);
      setTitle("");
      return;
    }

    (async () => {
      try {
        const data = await getMessages(chatId);
        setMessages(data.messages);
        setTitle(data.chat_title);
      } catch (err) {
        console.error(err);
      }
    })();
  }, [chatId]);

  // Auto scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, showTypingBubble]);

  // Auto resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        textareaRef.current.scrollHeight + "px";
    }
  }, [input]);

  // Stream response
  const streamBotMessage = (text) => {
    let i = 0;
    setShowTypingBubble(false);

    const botMsg = {
      role: "assistant",
      content: "",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, botMsg]);

    const interval = setInterval(() => {
      i++;
      botMsg.content = text.slice(0, i);

      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { ...botMsg };
        return updated;
      });

      if (i >= text.length) clearInterval(interval);
    }, 15);
  };

  const handleSend = async () => {
    if (!input.trim() || !agentId || loading) return;

    const wordCount = input.trim().split(/\s+/).length;
    if (wordCount > 250) {
      toast.info("Max 250 words allowed");
      return;
    }

    let activeChatId = chatId;

    if (!activeChatId) {
      try {
        const chat = await createChat(agentId);
        activeChatId = chat.id;
        navigate(`/${org}/agents/${agentId}/${activeChatId}`);
      } catch {
        toast.error("Failed to create chat");
        return;
      }
    }

    setMessages((prev) => [
      ...prev,
      { role: "user", content: input, timestamp: new Date() },
    ]);

    const messageText = input;
    setInput("");
    setLoading(true);
    setShowTypingBubble(true);

    try {
      const res = await sendMessage(activeChatId, messageText);
      streamBotMessage(res.answer);
    } catch {
      toast.error("Error sending message");
      setShowTypingBubble(false);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied!");
  };

  const formatTime = (date) => {
    if (!date) return "";
    return new Date(date).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="flex h-full bg-gray-50">
      <div className="flex flex-col flex-1">

        {/* CHAT */}
        <div className="flex-1 overflow-y-auto px-3 sm:px-6 py-4 space-y-4">

          {!chatId && (
            <div className="h-full flex items-center justify-center text-gray-400">
              Start a new conversation
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`group flex flex-col ${
                msg.role === "user" ? "items-end" : "items-start"
              }`}
            >
              <div
                className={`px-4 py-3 rounded-2xl shadow-sm max-w-[90%] sm:max-w-[75%] text-sm sm:text-base ${
                  msg.role === "user"
                    ? "bg-gray-800 text-white"
                    : "bg-white border"
                }`}
              >
                {msg.role === "assistant" ? (
                  <div className="prose prose-sm sm:prose-base max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  msg.content
                )}
              </div>

              {/* Meta */}
              <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 opacity-0 group-hover:opacity-100 transition">

                <span>{formatTime(msg.timestamp)}</span>

                {msg.role === "assistant" && (
                  <button onClick={() => copyToClipboard(msg.content)}>
                    Copy
                  </button>
                )}
              </div>
            </div>
          ))}

          {showTypingBubble && (
            <div className="typing-bubble">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* INPUT */}
        <div className="border-t bg-white p-3 sm:p-4">
          <div className="flex items-end gap-2">

            <textarea
              ref={textareaRef}
              rows={1}
              className="flex-1 resize-none px-3 py-2 border rounded-md focus:ring-2 focus:ring-gray-400 text-sm sm:text-base"
              placeholder="Type a message..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />

            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="px-4 py-2 bg-gray-900 text-white rounded-md hover:bg-gray-800 disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </div>

      {/* STYLES */}
      <style>
        {`
          .typing-bubble {
            display: flex;
            gap: 4px;
            padding: 8px 12px;
            background: #e5e7eb;
            border-radius: 12px;
            width: fit-content;
          }

          .dot {
            width: 6px;
            height: 6px;
            background: #555;
            border-radius: 50%;
            animation: bounce 1.2s infinite;
          }

          .dot:nth-child(2) { animation-delay: 0.2s; }
          .dot:nth-child(3) { animation-delay: 0.4s; }

          @keyframes bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1); }
          }

          pre {
            background: #111827;
            color: #f9fafb;
            padding: 12px;
            border-radius: 8px;
            overflow-x: auto;
          }

          code {
            font-size: 0.85em;
          }
        `}
      </style>
    </div>
  );
}