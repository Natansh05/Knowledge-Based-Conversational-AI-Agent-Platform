import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "../services/auth/useAuth";
import DocumentUploadModal from "../components/DocumentUploadModal";
import MultiSelectDropdown from "../components/MultiSelectDropdown";
import { useTitle } from "../components/layout/TitleContext";
import { useOutletContext } from "react-router-dom";
import DocumentUpdateModal from "../components/DocumentUpdateModal";
import toast from "react-hot-toast";

// Debounce helper
const debounce = (func, delay = 300) => {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => func(...args), delay);
  };
};

export default function DocumentsPage() {
  const { getDocs, fetchUsers, downloadDoc, user } = useAuth();
  const { setTitle } = useTitle();
  const { setTopBarActions } = useOutletContext() || {};

  const todayDateStr = new Date().toISOString().split("T")[0];

  const [documents, setDocuments] = useState([]);
  const [users, setUsers] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);

  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isUpdateModalOpen, setIsUpdateModalOpen] = useState(false);

  const [filters, setFilters] = useState({
    search: "",
    uploaded_by: [],
    file_type: [],
    status: "",
    start_date: todayDateStr,
    end_date: todayDateStr,
  });

  const [pagination, setPagination] = useState({
    page: 1,
    page_size: 10,
    num_pages: 1,
    current_page: 1,
  });

  const fileTypeOptions = [
    { id: "application/pdf", name: "PDF" },
    { id: "docx", name: "DOCX" },
    { id: "txt", name: "TXT" },
    { id: "text/csv", name: "CSV" },
  ];

  // Title
  useEffect(() => setTitle("Documents"), [setTitle]);

  // Top bar button
  useEffect(() => {
    if (setTopBarActions) {
      setTopBarActions(
        <button
          onClick={() => setIsUploadModalOpen(true)}
          className="h-8 px-3 text-sm bg-gray-900 text-white rounded hover:bg-gray-800"
        >
          Add New
        </button>
      );
    }
    return () => setTopBarActions?.(null);
  }, [setTopBarActions]);

  // Fetch users
  useEffect(() => {
    fetchUsers()
      .then(res => setUsers(res || []))
      .catch(() => toast.error("Failed to fetch users"));
  }, []);

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    try {
      const data = await getDocs(
        {
          ...filters,
          uploaded_by: filters.uploaded_by.join(","),
          file_type: filters.file_type.join(","),
        },
        pagination.page,
        pagination.page_size
      );

      setDocuments(data.results || []);
      setPagination(prev => ({
        ...prev,
        num_pages: data.num_pages || 1,
        current_page: data.current_page || 1,
      }));
    } catch {
      toast.error("Failed to fetch documents");
    }
  }, [
    getDocs,
    filters.search,
    filters.status,
    filters.start_date,
    filters.end_date,
    filters.uploaded_by.join(","),
    filters.file_type.join(","),
    pagination.page,
    pagination.page_size,
  ]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Handlers
  const handleFilterChange = e => {
    const { name, value } = e.target;
    setFilters(prev => ({ ...prev, [name]: value }));
    setPagination(prev => ({ ...prev, page: 1 }));
  };

  const handleUpdate = doc => {
    if (doc.uploaded_by !== user.id) {
      toast.error("Only owner can update the document");
      return;
    }
    setSelectedDoc(doc);
    setIsUpdateModalOpen(true);
  };

  const debouncedSearchChange = debounce(value => {
    setFilters(prev => ({ ...prev, search: value }));
    setPagination(prev => ({ ...prev, page: 1 }));
  });

  const formatFileSize = bytes => {
    if (!bytes) return "—";
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${sizes[i]}`;
  };

  return (
    <div className="p-4 md:p-6 bg-gray-50 min-h-screen">

      {/* FILTERS */}
      <div className="relative z-20 mb-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">

          {/* Search */}
          <div className="min-w-0 flex flex-col">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Search
            </label>
            <input
              type="text"
              placeholder="Search document..."
              onChange={e => debouncedSearchChange(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
            />
          </div>

          {/* Date */}
          <div className="min-w-0 sm:col-span-2 xl:col-span-1 flex flex-col">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Created Date
            </label>

            <div className="flex items-center gap-2">
              <input
                type="date"
                name="start_date"
                value={filters.start_date}
                onChange={handleFilterChange}
                className="flex-1 px-3 py-2 border rounded-md text-sm"
                aria-label="From date"
                placeholder="From"
              />

              <span className="text-gray-400 text-sm select-none">—</span>

              <input
                type="date"
                name="end_date"
                value={filters.end_date}
                onChange={handleFilterChange}
                className="flex-1 px-3 py-2 border rounded-md text-sm"
                aria-label="To date"
                placeholder="To"
              />
            </div>
          </div>

          {/* Uploaded By */}
          <div className="min-w-0 relative z-30 flex flex-col">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Users
            </label>
            <MultiSelectDropdown
              options={users}
              labelKey="username"
              valueKey="id"
              selectedValues={filters.uploaded_by}
              onChange={values =>
                setFilters(prev => ({ ...prev, uploaded_by: values }))
              }
              placeholder="Select Users"
            />
          </div>

          {/* File Type */}
          <div className="min-w-0 relative z-30 flex flex-col">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              File Types
            </label>
            <MultiSelectDropdown
              options={fileTypeOptions}
              labelKey="name"
              valueKey="id"
              selectedValues={filters.file_type}
              onChange={values =>
                setFilters(prev => ({ ...prev, file_type: values }))
              }
              placeholder="Select File Types"
            />
          </div>

          {/* Status */}
          <div className="min-w-0 flex flex-col">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Status
            </label>
            <select
              name="status"
              value={filters.status}
              onChange={handleFilterChange}
              className="w-full px-3 py-2 border rounded-md text-sm"
            >
              <option value="">All Status</option>
              <option value="uploaded">Uploaded</option>
              <option value="processing">Processing</option>
              <option value="ready">Ready</option>
              <option value="failed">Failed</option>
            </select>
          </div>

        </div>
      </div>

      {/* MOBILE CARDS */}
      <div className="md:hidden space-y-4">
        {documents.map(doc => (
          <div key={doc.id} className="bg-white p-4 rounded-lg shadow">
            <h3 className="font-semibold text-sm">{doc.name}</h3>

            <div className="text-xs text-gray-600 mt-2 space-y-1">
              <p>Type: {doc.file_type}</p>
              <p>Size: {formatFileSize(doc.file_size)}</p>
              <p>Status: {doc.status}</p>
              <p>
                Uploaded:{" "}
                {users.find(u => u.id === doc.uploaded_by)?.username}
              </p>
            </div>

            <div className="flex gap-3 mt-3">
              <button
                onClick={() => downloadDoc(doc.id)}
                className="text-green-600 text-xs"
              >
                Download
              </button>
              <button
                onClick={() => handleUpdate(doc)}
                className="text-blue-600 text-xs"
              >
                Update
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* DESKTOP TABLE */}
      <div className="hidden md:block bg-white rounded-lg shadow relative z-10">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-100">
              <tr>
                {["Name", "Type", "Size", "Status", "Actions"].map(h => (
                  <th key={h} className="px-4 py-2 text-xs text-left">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {documents.map(doc => (
                <tr key={doc.id} className="border-t">
                  <td className="px-4 py-2">{doc.name}</td>
                  <td className="px-4 py-2">{doc.file_type}</td>
                  <td className="px-4 py-2">
                    {formatFileSize(doc.file_size)}
                  </td>
                  <td className="px-4 py-2">{doc.status}</td>
                  <td className="px-4 py-2 flex gap-2">
                    <button
                      onClick={() => downloadDoc(doc.id)}
                      className="text-green-600 text-sm"
                    >
                      Download
                    </button>
                    <button
                      onClick={() => handleUpdate(doc)}
                      className="text-blue-600 text-sm"
                    >
                      Update
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* PAGINATION */}
      <div className="flex justify-center mt-4 gap-2 flex-wrap">
        {Array.from({ length: pagination.num_pages }, (_, i) => (
          <button
            key={i}
            onClick={() =>
              setPagination(prev => ({ ...prev, page: i + 1 }))
            }
            className="px-3 py-1 border rounded text-sm"
          >
            {i + 1}
          </button>
        ))}
      </div>

      {/* MODALS */}
      {isUploadModalOpen && (
        <DocumentUploadModal onClose={() => setIsUploadModalOpen(false)} />
      )}

      {isUpdateModalOpen && (
        <DocumentUpdateModal
          doc={selectedDoc}
          onClose={() => setIsUpdateModalOpen(false)}
          onSuccess={fetchDocuments}
        />
      )}
    </div>
  );
}
