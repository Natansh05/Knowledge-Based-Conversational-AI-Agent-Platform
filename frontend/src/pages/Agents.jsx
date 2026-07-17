import React, { useEffect, useState } from "react";
import { useAuth } from "../services/auth/useAuth";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { useTitle } from "../components/layout/TitleContext";
import usePageTitle from "../components/layout/usePageTitle";
import MultiSelectDropdown from "../components/MultiSelectDropdown";
import toast from "react-hot-toast";

const AgentsPage = () => {
  usePageTitle("Agents");

  const { getAgents, getTags, updateAgentStatus, deleteAgent } = useAuth();
  const navigate = useNavigate();
  const { org } = useParams();
  const { setTitle } = useTitle();
  const { setTopBarActions } = useOutletContext() || {};

  const [agents, setAgents] = useState([]);
  const [tags, setTags] = useState([]);
  const [filters, setFilters] = useState({ search: "", tag: [], status: "" });
  const [pagination, setPagination] = useState({ page: 1, page_size: 10, num_pages: 1, current_page: 1 });

  useEffect(() => setTitle("Agents"), [setTitle]);

  useEffect(() => {
    if (setTopBarActions) {
      setTopBarActions(
        <button
          onClick={() => navigate(`/${org}/agents/new`)}
          className="h-8 px-3 text-sm sm:text-base font-medium flex items-center justify-center bg-gray-900 text-white rounded hover:bg-gray-800"
        >
          + New Agent
        </button>
      );
    }
    return () => setTopBarActions?.(null);
  }, [setTopBarActions, navigate, org]);

  const fetchAgents = async () => {
    const data = await getAgents({ ...filters, tag: filters.tag.join(",") }, pagination.page, pagination.page_size);
    setAgents(data.results);
    setPagination((prev) => ({ ...prev, num_pages: data.num_pages, current_page: data.current_page }));
  };

  const fetchTags = async () => {
    try {
      const data = await getTags();
      setTags(data);
    } catch (err) {
      toast.error(err);
    }
  };

  useEffect(() => { fetchAgents(); }, [filters, pagination.page]);
  useEffect(() => { fetchTags(); }, []);

  const handleFilterChange = (e) => {
    setFilters({ ...filters, [e.target.name]: e.target.value });
    setPagination((prev) => ({ ...prev, page: 1 }));
  };

  const handleTagClick = (tagId) => {
    const exists = filters.tag.includes(tagId);
    const updated = exists ? filters.tag.filter((t) => t !== tagId) : [...filters.tag, tagId];
    setFilters({ ...filters, tag: updated });
  };

  const handlePageChange = (page) => setPagination({ ...pagination, page });

  const handleStatusToggle = async (agent) => {
    await updateAgentStatus(agent.id, !agent.is_active);
    fetchAgents();
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this agent?")) return;
    await deleteAgent(id);
    toast.success("Agent deleted successfully");
    fetchAgents();
  };

  const handleStartChat = (agentId) => navigate(`/${org}/agents/${agentId}`);

  return (
    <div className="p-2 sm:p-4 md:p-6 bg-gray-50 min-h-screen">

      {/* Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 mb-6">
        <div>
          <label className="block text-sm font-medium mb-1">Search</label>
          <input
            name="search"
            value={filters.search}
            onChange={handleFilterChange}
            placeholder="Agent name"
            className="w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-gray-400 text-sm sm:text-base"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Tag</label>
          <MultiSelectDropdown
            options={tags}
            labelKey="name"
            valueKey="id"
            selectedValues={filters.tag}
            onChange={(values) => {
              setFilters({ ...filters, tag: values });
              setPagination((prev) => ({ ...prev, page: 1 }));
            }}
            placeholder="Select tags"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Status</label>
          <select
            name="status"
            value={filters.status}
            onChange={handleFilterChange}
            className="w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-gray-400 text-sm sm:text-base"
          >
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>
      </div>

      {/* Desktop Table */}
      <div className="hidden md:block overflow-x-auto bg-white rounded-lg shadow-md max-h-[600px]">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-100 sticky top-0">
            <tr>
              {["Name","Description","Document","Tags","Status","Actions"].map((col) => (
                <th key={col} className="px-4 py-2 text-left text-xs sm:text-sm font-medium text-gray-500 uppercase">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {agents.length === 0 ? (
              <tr>
                <td colSpan="6" className="text-center py-6 text-gray-500">No agents found</td>
              </tr>
            ) : (
              agents.map((agent) => (
                <tr key={agent.id}>
                  <td className="px-4 py-2">{agent.name}</td>
                  <td className="px-4 py-2">{agent.description}</td>
                  <td className="px-4 py-2">{agent.document_names?.join(", ")}</td>
                  <td className="px-4 py-2 flex flex-wrap gap-1">
                    {agent.tags_detail?.map((tag) => (
                      <span
                        key={tag.id}
                        onClick={() => handleTagClick(tag.id)}
                        className={`px-2 py-1 text-xs rounded cursor-pointer ${filters.tag.includes(tag.id) ? "bg-gray-900 text-white" : "bg-gray-200 hover:bg-gray-300"}`}
                      >
                        {tag.name}
                      </span>
                    ))}
                  </td>
                  <td className="px-4 py-2">
                    <input type="checkbox" checked={agent.is_active} onChange={() => handleStatusToggle(agent)} />
                  </td>
                  <td className="px-4 py-2 space-x-2">
                    <button onClick={() => navigate(`/${org}/agents/${agent.id}/edit`)} className="text-xs sm:text-sm text-blue-600 hover:underline">Edit</button>
                    <button onClick={() => handleDelete(agent.id)} className="text-xs sm:text-sm text-red-600 hover:underline">Delete</button>
                    <button onClick={() => handleStartChat(agent.id)} className="text-xs sm:text-sm text-gray-800 hover:underline">Chat</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile Cards */}
      <div className="md:hidden space-y-4">
        {agents.length === 0 ? (
          <p className="text-center text-gray-500 py-6">No agents found</p>
        ) : (
          agents.map((agent) => (
            <div key={agent.id} className="bg-white rounded-lg shadow p-4">
              <h3 className="font-semibold text-sm sm:text-base mb-1">{agent.name}</h3>
              <p className="text-xs sm:text-sm text-gray-600 mb-1">{agent.description}</p>
              <p className="text-xs sm:text-sm text-gray-600 mb-1">
                <strong>Documents:</strong> {agent.document_names?.join(", ") || "None"}
              </p>
              <div className="flex flex-wrap gap-1 mb-1">
                {agent.tags_detail?.map(tag => (
                  <span
                    key={tag.id}
                    onClick={() => handleTagClick(tag.id)}
                    className={`px-2 py-1 text-xs rounded cursor-pointer ${filters.tag.includes(tag.id) ? "bg-gray-900 text-white" : "bg-gray-200 hover:bg-gray-300"}`}
                  >
                    {tag.name}
                  </span>
                ))}
              </div>
              <div className="flex items-center justify-between mt-2">
                <label className="flex items-center gap-1 text-xs">
                  <input type="checkbox" checked={agent.is_active} onChange={() => handleStatusToggle(agent)} />
                  Active
                </label>
                <div className="flex gap-2">
                  <button onClick={() => navigate(`/${org}/agents/${agent.id}/edit`)} className="text-xs text-blue-600 hover:underline">Edit</button>
                  <button onClick={() => handleDelete(agent.id)} className="text-xs text-red-600 hover:underline">Delete</button>
                  <button onClick={() => handleStartChat(agent.id)} className="text-xs text-gray-800 hover:underline">Chat</button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      <div className="flex justify-center mt-4 gap-2 flex-wrap">
        {Array.from({ length: pagination.num_pages }, (_, i) => (
          <button
            key={i + 1}
            onClick={() => handlePageChange(i + 1)}
            className={`px-2 sm:px-3 py-1 rounded-md border ${pagination.current_page === i + 1 ? "bg-gray-900 text-white" : "bg-white hover:bg-gray-100"} text-xs sm:text-sm`}
          >
            {i + 1}
          </button>
        ))}
      </div>

    </div>
  );
};

export default AgentsPage;