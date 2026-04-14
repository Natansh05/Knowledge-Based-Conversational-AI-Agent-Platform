import { useEffect, useState } from "react";
import { useAuth } from "../services/auth/useAuth";
import usePageTitle from "../components/layout/usePageTitle";
import {
  BarChart,
  Bar,
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

        <MetricCard
          title="Total Chats"
          value={usage.total_chats}
        />

        <MetricCard
          title="Total Questions"
          value={usage.total_questions}
        />

        <MetricCard
          title="Total Users"
          value={usage.total_users}
        />

        <MetricCard
          title="Active Users (7d)"
          value={usage.active_users_7d}
        />

      </div>

      {/* Knowledge Base */}
      <div className="grid gap-6 md:grid-cols-2 mb-8">

        <MetricCard
          title="Documents"
          value={kb.total_documents}
        />

        <MetricCard
          title="Chunks"
          value={kb.total_chunks}
        />

      </div>

      {/* Engagement */}
      <div className="grid gap-6 md:grid-cols-2 mb-8">

        <MetricCard
          title="Avg Messages per Chat"
          value={
            engagement.avg_messages_per_chat
              ? engagement.avg_messages_per_chat.toFixed(2)
              : 0
          }
        />

      </div>

      {/* Agent Usage */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">

        <h2 className="text-lg font-semibold text-gray-800 mb-4">
            Agent Usage
        </h2>

        {agent_usage.length === 0 ? (
            <p className="text-gray-500 text-sm">
            No usage data yet
            </p>
        ) : (
            <ResponsiveContainer width="100%" height={300}>
            <BarChart
                data={agent_usage.map(agent => ({
                name: agent.agent__name,
                chats: agent.chat_count,
                }))}
                margin={{ top: 10, right: 20, left: -10, bottom: 0 }}
            >
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />

                <XAxis
                dataKey="name"
                tick={{ fontSize: 12 }}
                stroke="#888"
                />

                <YAxis stroke="#888" />

                <Tooltip
                contentStyle={{
                    borderRadius: "8px",
                    border: "1px solid #e5e7eb",
                }}
                />

                <Bar
                dataKey="chats"
                fill="#6366f1"
                radius={[8, 8, 0, 0]}
                />
            </BarChart>
            </ResponsiveContainer>
        )}

        </div>

    </div>
  );
}

function MetricCard({ title, value }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 hover:shadow-md transition">
      
      <p className="text-sm text-gray-500">
        {title}
      </p>

      <p className="mt-2 text-2xl font-semibold text-gray-800">
        {value}
      </p>

    </div>
  );
}