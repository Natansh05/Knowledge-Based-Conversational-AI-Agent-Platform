import { useEffect, useState } from "react";
import { useAuth } from "../services/auth/useAuth";
import usePageTitle from "../components/layout/usePageTitle";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";


export default function Dashboard() {
  const { getMetrics } = useAuth();
  usePageTitle("Dashboard Metrics")

  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadMetrics() {
      try {
        const data = await getMetrics();
        setMetrics(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadMetrics();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        Loading dashboard...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-red-500">
        {error}
      </div>
    );
  }

  const usage = metrics.usage;
  const kb = metrics.knowledge_base;
  const engagement = metrics.engagement;
  const agent_usage = metrics.agent_usage;
  const rag = metrics.rag_quality;

  return (
    <div className="h-full overflow-y-auto bg-gray-50 p-6">

      {/* Page Header */}
      <div className="mb-8">
        <p className="text-gray-500 text-sm">
          Overview of your AI knowledge system
        </p>
      </div>

      {/* Usage Metrics */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <MetricCard title="Total Chats" value={usage.total_chats} />
        <MetricCard title="Total Questions" value={usage.total_questions} />
        <MetricCard title="Total Users" value={usage.total_users} />
        <MetricCard title="Active Users (7d)" value={usage.active_users_7d} />
      </div>

      {/* Knowledge Base */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <MetricCard title="Documents" value={kb.total_documents} />
        <MetricCard title="Chunks" value={kb.total_chunks} />
        <MetricCard title="Avg Chunks / Document" value={kb.avg_chunks_per_document} />
        <MetricCard title="Document Coverage" value={`${kb.coverage_pct}%`} />
      </div>

      {/* Engagement */}
      <div className="grid gap-6 sm:grid-cols-3 mb-8">
        <MetricCard
          title="Avg Messages per Chat"
          value={engagement.avg_messages_per_chat ? engagement.avg_messages_per_chat.toFixed(2) : 0}
        />
        <MetricCard title="Answer Success Rate" value={`${rag.success_rate_pct}%`} />
        <MetricCard title="Avg Confidence" value={rag.avg_confidence.toFixed(3)} />
      </div>

      {/* Knowledge Gap */}
      <div className="grid gap-6 sm:grid-cols-2 mb-8">
        <MetricCard title="Knowledge Gaps" value={rag.knowledge_gap_count} />
        <MetricCard title="Unused Documents" value={kb.unused_documents.length} />
      </div>

      {/* Chats Per Day */}
      <ChatsPerDayChart data={engagement.chats_per_day} />

      {/* Agent Usage */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Agent Usage (Top 5)</h2>
        {agent_usage.length === 0 ? (
          <p className="text-gray-500 text-sm">No usage data yet</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart
              data={agent_usage.map(a => ({ name: a.agent__name, chats: a.chat_count }))}
              margin={{ top: 10, right: 20, left: -10, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#888" />
              <YAxis stroke="#888" />
              <Tooltip contentStyle={{ borderRadius: "8px", border: "1px solid #e5e7eb" }} />
              <Bar dataKey="chats" fill="#6366f1" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Questions Per Agent */}
      <QuestionsPerAgentChart data={engagement.questions_per_agent} />

      {/* Most Referenced Documents */}
      <HorizontalBarChart
        title="Most Referenced Documents"
        data={kb.most_used_documents.map(d => ({ name: d.name, value: d.retrieval_count }))}
        dataKey="value"
        color="#10b981"
        label="Retrievals"
      />

      {/* Questions Per Document */}
      <HorizontalBarChart
        title="Questions Answered per Document"
        data={kb.questions_per_document.map(d => ({ name: d.name, value: d.question_count }))}
        dataKey="value"
        color="#f59e0b"
        label="Questions"
      />

      {/* Unused Documents */}
      <UnusedDocsList docs={kb.unused_documents} />

    </div>
  );
}

function MetricCard({ title, value }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 hover:shadow-md transition">
      <p className="text-sm text-gray-500">{title}</p>
      <p className="mt-2 text-2xl font-semibold text-gray-800">{value}</p>
    </div>
  );
}

function ChatsPerDayChart({ data }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Chats Per Day (Last 30 Days)</h2>
      {data.length === 0 ? (
        <p className="text-gray-500 text-sm">No chat activity in the last 30 days</p>
      ) : (
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={data} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#888" />
            <YAxis stroke="#888" allowDecimals={false} />
            <Tooltip contentStyle={{ borderRadius: "8px", border: "1px solid #e5e7eb" }} />
            <Line type="monotone" dataKey="chats" stroke="#6366f1" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function QuestionsPerAgentChart({ data }) {
  const chartData = data.map(d => ({
    name: d.agent__name,
    questions: parseFloat((d.avg_questions || 0).toFixed(1)),
  }));

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Avg Questions per Chat per Agent</h2>
      {chartData.length === 0 ? (
        <p className="text-gray-500 text-sm">No data yet</p>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="#888" />
            <YAxis stroke="#888" />
            <Tooltip contentStyle={{ borderRadius: "8px", border: "1px solid #e5e7eb" }} />
            <Bar dataKey="questions" fill="#f59e0b" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function HorizontalBarChart({ title, data, dataKey, color, label }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">{title}</h2>
      {data.length === 0 ? (
        <p className="text-gray-500 text-sm">No data yet</p>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(200, data.length * 40)}>
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis type="number" stroke="#888" allowDecimals={false} />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fontSize: 11 }}
              stroke="#888"
              width={120}
            />
            <Tooltip
              formatter={(val) => [val, label]}
              contentStyle={{ borderRadius: "8px", border: "1px solid #e5e7eb" }}
            />
            <Bar dataKey={dataKey} fill={color} radius={[0, 6, 6, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function UnusedDocsList({ docs }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8">
      <h2 className="text-lg font-semibold text-gray-800 mb-1">Unused Documents</h2>
      <p className="text-sm text-gray-500 mb-4">
        {docs.length === 0
          ? "All documents have been referenced in at least one conversation."
          : `${docs.length} document(s) have never been retrieved in any conversation.`}
      </p>
      {docs.length > 0 && (
        <ul className="divide-y divide-gray-100">
          {docs.map(doc => (
            <li key={doc.id} className="py-2 text-sm text-gray-700">{doc.name}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
