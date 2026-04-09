import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useAuth } from "../services/auth/useAuth";

export default function ForgotPassword() {
  const { org } = useParams();
  const { forgotPassword } = useAuth();

  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (loading) return;

    setMessage("");
    setError("");
    setLoading(true);

    try {
      const res = await forgotPassword(email);
      setMessage(
        res.detail || "Password reset instructions sent to your email."
      );
    } catch (err) {
      setError(err.message || "Something went wrong. Try again later.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-2 sm:px-4 md:px-0 py-6">
      <div className="bg-white rounded-lg shadow-md w-full sm:w-full md:max-w-md p-6 sm:p-8 mx-auto">
        
        <h2 className="text-xl sm:text-2xl font-semibold mb-4 text-center">
          Forgot Password
        </h2>

        <p className="text-center text-gray-600 mb-5 sm:mb-6 text-sm sm:text-base">
          Enter your email to reset password for{" "}
          <span className="font-medium text-gray-800 break-all">{org}</span>
        </p>

        <form className="space-y-4 sm:space-y-5" onSubmit={handleSubmit}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full border border-gray-300 rounded-md px-3 sm:px-4 py-2 sm:py-2.5 text-sm sm:text-base focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />

          <button
            type="submit"
            disabled={loading}
            className={`w-full font-semibold py-2.5 sm:py-3 rounded-md transition text-sm sm:text-base
              ${loading
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-indigo-600 hover:bg-indigo-700 text-white"
              }`}
          >
            {loading ? "Sending..." : "Reset Password"}
          </button>

          {message && (
            <p className="text-center text-green-600 font-medium text-sm sm:text-base mt-2">
              {message}
            </p>
          )}
          {error && (
            <p className="text-center text-red-600 font-medium text-sm sm:text-base mt-2">
              {error}
            </p>
          )}
        </form>

        {/* Back to Login */}
        <div className="mt-6 text-center">
          <Link
            to={`/${org}/login`}
            className="text-sm sm:text-base text-indigo-600 hover:underline font-medium"
          >
            ← Back to Login
          </Link>
        </div>
      </div>
    </div>
  );
}