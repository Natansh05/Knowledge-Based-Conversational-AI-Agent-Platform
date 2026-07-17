import { useState, useEffect } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useAuth } from "../services/auth/useAuth"

export default function Invite() {
  const { org, token } = useParams()
  const navigate = useNavigate()
  const { validateInvite, acceptInvite } = useAuth()

  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [email, setEmail] = useState("")
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  // -------------------------------
  // Validate token on mount
  // -------------------------------
  useEffect(() => {
    let mounted = true

    async function checkInvite() {
      try {
        const data = await validateInvite({ org, token })
        if (mounted) setEmail(data.email)
      } catch (err) {
        if (mounted) setError(err.message || "Invalid invite token")
      } finally {
        if (mounted) setLoading(false)
      }
    }

    checkInvite()
    return () => { mounted = false }
  }, [org, token, validateInvite])

  // -------------------------------
  // Handle form submit
  // -------------------------------
  async function handleSubmit(e) {
    e.preventDefault()
    if (submitting) return

    setError("")
    setSubmitting(true)

    try {
      await acceptInvite({ org, token, username, password })
      navigate(`/${org}/dashboard`)
    } catch (err) {
      setError(err.message || "Failed to accept invite")
    } finally {
      setSubmitting(false)
    }
  }

  // -------------------------------
  // Loading state
  // -------------------------------
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="bg-white p-6 rounded-lg shadow-md w-full sm:w-full md:max-w-md text-center">
          Validating invite...
        </div>
      </div>
    )
  }

  // -------------------------------
  // Error state
  // -------------------------------
  if (error && !email) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="bg-white p-6 rounded-lg shadow-md w-full sm:w-full md:max-w-md text-center">
          <h2 className="text-xl font-semibold mb-2">Invite Error</h2>
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    )
  }

  // -------------------------------
  // Main form
  // -------------------------------
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-2 sm:px-4 md:px-0 py-6">
      <div className="bg-white rounded-lg shadow-md w-full sm:w-full md:max-w-md p-6 sm:p-8 mx-auto">
        
        <h2 className="text-xl sm:text-2xl font-semibold mb-4 text-center">
          Accept Invite to {org}
        </h2>

        <p className="text-center mb-4 text-gray-700">
          <strong>Email:</strong> {email || "Loading..."}
        </p>

        <form className="space-y-4 sm:space-y-5" onSubmit={handleSubmit}>

          <input
            type="text"
            placeholder="Choose Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            className="w-full border border-gray-300 rounded-md px-3 sm:px-4 py-2 sm:py-2.5 text-sm sm:text-base focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />

          <input
            type="password"
            placeholder="Choose Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full border border-gray-300 rounded-md px-3 sm:px-4 py-2 sm:py-2.5 text-sm sm:text-base focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />

          <button
            type="submit"
            disabled={submitting}
            className={`w-full font-semibold py-2.5 sm:py-3 rounded-md transition text-sm sm:text-base
              ${submitting
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-indigo-600 hover:bg-indigo-700 text-white"
              }`}
          >
            {submitting ? "Creating Account..." : "Create Account"}
          </button>

          {error && email && (
            <p className="text-red-600 text-center font-medium text-sm sm:text-base mt-2">
              {error}
            </p>
          )}

        </form>
      </div>
    </div>
  )
}