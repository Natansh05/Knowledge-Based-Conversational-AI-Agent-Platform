import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../services/auth/useAuth";
import { toast } from "react-hot-toast";

export default function Login() {
  const { org } = useParams();
  const navigate = useNavigate();
  const { login } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (loading) return;

    setLoading(true);
    setError("");

    try {
      await login({ username, password, org });
      toast.success("Login Successful!!");
      navigate(`/${org}/metrics`);
    } catch (err) {
      console.error("Login error:", err);
      setError("Invalid credentials");
      toast.error("Login Failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 sm:px-6 py-6 overflow-x-hidden">
      {/* Card */}
      <div className="bg-white rounded-lg shadow-md w-full 
                      max-w-sm sm:max-w-md md:max-w-md 
                      p-6 sm:p-8 md:p-8">
        {/* Title */}
        <h2 className="text-2xl sm:text-2xl md:text-2xl font-semibold mb-3 text-center">
          User Login
        </h2>

        {/* Subtitle */}
        <p className="text-center text-gray-600 text-sm sm:text-base mb-5 sm:mb-6 break-words">
          Sign in for: <span className="font-medium text-gray-800">{org}</span>
        </p>

        <form className="space-y-4 sm:space-y-5" onSubmit={handleSubmit}>
          {/* Username */}
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            className="w-full border border-gray-300 rounded-md px-3 sm:px-4 py-2 sm:py-2.5 text-sm sm:text-base focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />

          {/* Password */}
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full border border-gray-300 rounded-md px-3 sm:px-4 py-2 sm:py-2.5 text-sm sm:text-base focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />

          {/* Login Button */}
          <button
            type="submit"
            disabled={loading}
            className={`w-full font-semibold py-2.5 sm:py-3 rounded-md transition text-sm sm:text-base
              ${
                loading
                  ? "bg-gray-400 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-700 text-white"
              }`}
          >
            {loading ? "Logging in..." : "Login"}
          </button>

          {/* Forgot Password */}
          <p className="text-center">
            <button
              type="button"
              onClick={() => navigate(`/${org}/forgot-password`)}
              className="text-indigo-600 hover:underline font-medium text-sm sm:text-base"
            >
              Forgot Password?
            </button>
          </p>

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