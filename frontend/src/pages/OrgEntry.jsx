import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/axios";

export default function OrgEntry() {
  const [org, setOrg] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    if (!org) return;

    try {
      const res = await api.get(`/${org}/`);
      if (res.status === 200) navigate(`/${org}/login`);
      else setError("Tenant not found");
    } catch {
      setError("Tenant does not exist");
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-2 sm:px-4 md:px-0 py-6">
      
      {/* Card */}
      <div className="bg-white rounded-lg shadow-md w-full
                      sm:w-full md:max-w-md
                      p-6 sm:p-8 md:p-8
                      mx-auto">
        
        {/* Title */}
        <h2 className="text-xl sm:text-2xl font-semibold mb-4 text-center">
          Enter your organization
        </h2>

        <form className="space-y-4 sm:space-y-5" onSubmit={handleSubmit}>
          
          {/* Input with prefix */}
          <div className="flex border border-gray-300 rounded-md overflow-hidden focus-within:ring-2 focus-within:ring-indigo-400">
            <span className="px-3 py-2 bg-gray-100 text-gray-600 select-none text-sm sm:text-base">
              kbc.com/
            </span>
            <input
              type="text"
              placeholder="your-org"
              value={org}
              onChange={(e) => setOrg(e.target.value)}
              className="flex-1 px-3 py-2 sm:py-2.5 text-sm sm:text-base focus:outline-none"
              required
            />
          </div>

          {/* Continue button */}
          <button
            type="submit"
            className="w-full bg-indigo-600 text-white font-semibold py-2.5 sm:py-3 rounded-md text-sm sm:text-base hover:bg-indigo-700 transition"
          >
            Continue
          </button>

          {/* Error */}
          {error && (
            <p className="text-red-600 text-center font-medium text-sm sm:text-base mt-2">
              {error}
            </p>
          )}
        </form>
      </div>
    </div>
  );
}