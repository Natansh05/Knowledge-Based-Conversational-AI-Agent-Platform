import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import toast from "react-hot-toast";
import { useAuth } from "../services/auth/useAuth";
import TagSelector from "../components/TagSelector";
import MultiSelectDropdown from "../components/MultiSelectDropdown";

const CreateEditAgentPage = () => {
  const { getDocs, createAgent, getAgentById, updateAgent, getTags, createTag } = useAuth();
  const navigate = useNavigate();
  const { org, agentId } = useParams();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [selectedDocuments, setSelectedDocuments] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [selectedTags, setSelectedTags] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [loadingAgent, setLoadingAgent] = useState(false);
  const [creatingOrUpdating, setCreatingOrUpdating] = useState(false);

  const isEditMode = Boolean(agentId);

  // Warn before leaving unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (name || systemPrompt || selectedDocuments.length || selectedTags.length) {
        e.preventDefault();
        e.returnValue = "You have unsaved changes. Are you sure you want to leave?";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [name, systemPrompt, selectedDocuments, selectedTags]);

  // Fetch documents
  useEffect(() => {
    const fetchAllDocs = async () => {
      setLoadingDocs(true);
      try {
        let allDocs = [];
        let page = 1;
        let totalPages = 1;

        do {
          const data = await getDocs({ status: "ready" }, page, 50);
          allDocs = [...allDocs, ...data.results.filter(doc => doc.status === "ready")];
          totalPages = Math.ceil(data.count / 50);
          page++;
        } while (page <= totalPages);

        setDocuments(allDocs);
      } catch (err) {
        console.error(err);
        toast.error("Error fetching documents");
      } finally {
        setLoadingDocs(false);
      }
    };

    fetchAllDocs();
  }, [getDocs]);

  // Fetch agent (edit mode)
  useEffect(() => {
    if (!isEditMode) return;

    const fetchAgent = async () => {
      setLoadingAgent(true);
      try {
        const agent = await getAgentById(agentId);
        setName(agent.name);
        setDescription(agent.description || "");
        setSystemPrompt(agent.system_prompt || "");
        setSelectedDocuments(agent.documents_detail || []);
        setSelectedTags(agent.tags_detail || []);
      } catch (err) {
        console.error(err);
        toast.error("Failed to load agent details");
      } finally {
        setLoadingAgent(false);
      }
    };

    fetchAgent();
  }, [agentId, getAgentById, isEditMode]);

  const handleSubmit = async () => {
    if (!name || !systemPrompt || selectedDocuments.length === 0) {
      toast.error("Please fill all required fields");
      return;
    }

    try {
      setCreatingOrUpdating(true);

      const payload = {
        name,
        description,
        system_prompt: systemPrompt,
        documents: selectedDocuments.map(d => d.id),
        tags: selectedTags.map(t => t.id),
      };

      if (isEditMode) {
        await updateAgent(agentId, payload);
        toast.success("Agent updated successfully");
      } else {
        await createAgent(payload);
        toast.success("Agent created successfully");
      }

      navigate(`/${org}/agents`);
    } catch (err) {
      console.error(err);
      toast.error(err.response?.data?.detail || err.message || "Error saving agent");
    } finally {
      setCreatingOrUpdating(false);
    }
  };

  if (isEditMode && loadingAgent) {
    return <p className="p-6 text-sm text-gray-500">Loading agent...</p>;
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 lg:gap-8">

          {/* LEFT SIDE */}
          <div className="md:col-span-2 space-y-5 sm:space-y-6">

            <button
              onClick={() => navigate(`/${org}/agents`)}
              className="text-sm text-gray-500 hover:text-gray-800"
            >
              ← Back to Agents
            </button>

            <div>
              <h1 className="text-2xl sm:text-3xl font-semibold text-gray-900">
                {isEditMode ? "Edit Agent" : "Create New Agent"}
              </h1>
              <p className="text-gray-500 text-sm mt-1">
                Define your agent’s behavior and knowledge sources.
              </p>
            </div>

            {/* Basic Info */}
            <div className="bg-white p-4 sm:p-6 rounded-xl shadow-sm border space-y-4">
              <h2 className="text-base sm:text-lg font-medium">Basic Info</h2>

              <input
                className="w-full border rounded-md px-3 py-2 text-sm sm:text-base focus:ring-2 focus:ring-gray-300"
                placeholder="Agent Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />

              <textarea
                className="w-full border rounded-md px-3 py-2 text-sm sm:text-base focus:ring-2 focus:ring-gray-300"
                placeholder="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>

            {/* System Prompt */}
            <div className="bg-white p-4 sm:p-6 rounded-xl shadow-sm border space-y-2">
              <h2 className="text-base sm:text-lg font-medium">🧠 System Prompt</h2>

              <textarea
                className="w-full border rounded-md px-3 py-3 font-mono text-xs sm:text-sm focus:ring-2 focus:ring-gray-300"
                style={{ minHeight: "180px" }}
                placeholder="Define how the agent should behave..."
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
              />
            </div>

            {/* Documents */}
            <div className="bg-white p-4 sm:p-6 rounded-xl shadow-sm border space-y-3">
              <h2 className="text-base sm:text-lg font-medium">📄 Documents</h2>

              {loadingDocs ? (
                <p className="text-sm text-gray-500">Loading documents...</p>
              ) : (
                <MultiSelectDropdown
                  options={documents}
                  selectedValues={selectedDocuments.map(d => d.id)}
                  onChange={(ids) => {
                    const selectedDocs = documents.filter(doc => ids.includes(doc.id));
                    setSelectedDocuments(selectedDocs);
                  }}
                  labelKey="name"
                  valueKey="id"
                  placeholder="Select documents"
                />
              )}
            </div>

            {/* Tags */}
            <div className="bg-white p-4 sm:p-6 rounded-xl shadow-sm border">
              <h2 className="text-base sm:text-lg font-medium mb-2">🏷️ Tags</h2>

              <TagSelector
                selectedTags={selectedTags}
                setSelectedTags={setSelectedTags}
                getTags={getTags}
                createTag={createTag}
              />
            </div>

            {/* Submit */}
            <div className="pt-2">
              <button
                onClick={handleSubmit}
                disabled={creatingOrUpdating}
                className="w-full sm:w-auto px-6 py-2 bg-gray-900 text-white rounded-md hover:bg-gray-800 disabled:opacity-50"
              >
                {creatingOrUpdating
                  ? (isEditMode ? "Updating..." : "Creating...")
                  : (isEditMode ? "Update Agent" : "Create Agent")}
              </button>
            </div>
          </div>

          {/* RIGHT SIDE (Tips) */}
          <div className="md:col-span-2 lg:col-span-1">
            <div className="bg-white p-4 sm:p-6 rounded-xl shadow-sm border space-y-2 lg:sticky lg:top-6">
              <h3 className="font-semibold text-gray-900">💡 Tips</h3>

              <ul className="text-sm text-gray-500 list-disc list-inside space-y-1">
                <li>System Prompt defines behavior and tone.</li>
                <li>Attach relevant documents for better responses.</li>
                <li>Use tags for easy organization.</li>
                <li>Description is optional; others are required.</li>
              </ul>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

export default CreateEditAgentPage;