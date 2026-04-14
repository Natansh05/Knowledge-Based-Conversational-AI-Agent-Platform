import { createContext, useEffect, useState } from "react"
import { api } from "../../api/axios"
import { getOrgFromPath } from "../../helpers/getTenant"
import { useLocation } from "react-router-dom"

export const AuthContext = createContext()

export function AuthProvider({ children }) {
  const tenant = getOrgFromPath() // e.g., "acme"
  const [user, setUser] = useState(null)
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false) // to prevent concurrent refreshes

  // -------------------------------
  // Initialize session on mount
  // -------------------------------

  const location = useLocation()
  useEffect(() => {
    if (!location.pathname.includes("/invite/")) {
      checkSession()
    } else {
      setLoading(false)
    }
  }, [tenant])
  // -------------------------------
  // Check current session
  // -------------------------------
  async function checkSession() {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get(`/${tenant}/users/profile/`)
      setUser(res.data)
    } catch (err) {
      setUser(null)
      if (err.response && err.response.status !== 401) {
        setError("Failed to load session")
      }
    } finally {
      setLoading(false)
    }
  }

  // -------------------------------
  // Login function
  // -------------------------------
  async function login(data) {
    setError(null)
    try {
      await api.post(`/${tenant}/api/token/`, data)
      await checkSession()
    } catch (err) {
      setUser(null)
      setError("Invalid credentials")
      throw err // so the form can handle it too
    }
  }

  // -------------------------------
  // Logout function
  // -------------------------------
  async function logout() {
    try {
      await api.post(`/${tenant}/api/logout/`)
    } catch (err) {
      console.error("Logout error:", err)
    } finally {
      setUser(null)
    }
  }

  // -------------------------------
  // Refresh token function
  // -------------------------------
  async function refresh() {
    if (refreshing) return // prevent multiple calls
    setRefreshing(true)
    try {
      await api.post(`/${tenant}/api/token/refresh/`)
      await checkSession()
    } catch (err) {
      console.error("Refresh failed:", err)
      setUser(null)
    } finally {
      setRefreshing(false)
    }
  }


  // -------------------------------
  // Validate Invite
  // -------------------------------
  async function validateInvite({org, token}) {
    try {
      const res = await api.post(`/${tenant}/users/invite/`, {
        token,
      })
      return res.data
    } catch (err) {
      throw new Error(
        err.response?.data?.detail || "Invalid or expired invite"
      )
    }
  }

  // -------------------------------
  // Accept Invite
  // -------------------------------
  async function acceptInvite({ token, username, password }) {
    try {
      await api.post(`/${tenant}/users/invite/`, {
        token,
        username,
        password,
      })

      // After successful invite completion,
      // backend already sets cookies OR returns tokens.
      // We now refresh session.
      await checkSession()
    } catch (err) {
      throw new Error(
        err.response?.data?.detail || "Failed to complete invite"
      )
    }
  }

  async function fetchUsers(){
    try{
      const res = await api.get(`/${tenant}/users/`)
      setUsers(res.data)
      console.log(res.data)
      return res.data
    } catch(err){
      throw new Error(
        err.response?.data?.detail || "Failed to fetch users"
      )
    }
  }

  async function updateUser(userData) {
    try {
      const updatedUser = await api.patch(`/${tenant}/users/profile/`, userData)
      setUser(updatedUser.data)
    } catch (err) {
      throw new Error(
        err.response?.data?.detail || "Failed to update user details"
      )
    }
  }


  async function getInvitedUsers() {
    try {
      const res = await api.get(`/${tenant}/users/invites/`)
      return res.data
    } catch (err) {
      throw new Error(
        err.response?.data?.detail || "Failed to fetch invited users"
      )
    }
  }

  async function sendInvite(email){
    try {
      await api.post(`/${tenant}/users/invite/send/`, email)
    } catch (err) {
      throw new Error(
        err.response?.data?.detail || "Failed to send invite"
      )
    }
  }

  async function getDocs(filters = {}, page = 1, pageSize = 10) {
    try {
      const params = new URLSearchParams({
        page,
        page_size: pageSize,
        ...filters,
      });

      const res = await api.get(`/${tenant}/api/docs/?${params.toString()}`);
      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to fetch documents");
    }
  }

  async function downloadDoc(documentId) {
    try {
      const params = new URLSearchParams({
        document_id: documentId,
      });

      const res = await api.get(
        `/${tenant}/api/docs/download/?${params.toString()}`
      );

      const { download_url, filename } = res.data;

      // Option 1: open in new tab (simplest)
      window.open(download_url, "_blank");

      // Option 2 (optional): force download with filename
      // const link = document.createElement("a");
      // link.href = download_url;
      // link.setAttribute("download", filename);
      // document.body.appendChild(link);
      // link.click();
      // link.remove();

      return res.data;
    } catch (err) {
      throw new Error(
        err.response?.data?.error || "Failed to download document"
      );
    }
  }

// -------------------- Update Document --------------------
  async function updateDoc(formData) {
    try {
      const res = await api.patch(
        `/${tenant}/api/docs/update/`,
        formData
      );

      return res.data;
    } catch (err) {
      throw new Error(
        err.response?.data?.error || "Failed to update document"
      );
    }
  }

  // -------------------- Delete Document --------------------
  async function deleteDoc(documentId) {
    try {
      // Send document_id as query param
      const params = new URLSearchParams({ document_id: documentId });

      const res = await api.delete(`/${tenant}/api/docs/delete/?${params.toString()}`);

      return res.data;
    } catch (err) {
      throw new Error(
        err.response?.data?.error || "Failed to delete document"
      );
    }
  }

  async function uploadDoc(file){
    try{
      const formData = new FormData()
      formData.append("file",file)

      const response = await api.post(
        `/${tenant}/api/upload/`,
        formData, 
        { 
          headers: 
          { 
            "Content-Type": "multipart/form-data" 
          } 
        }
      )

      return response.data

    } catch(err){
      throw new Error(err.response?.data?.detail || "File Upload Failed")
    }
  }

  async function getAgents(filters = {}, page = 1, pageSize = 10) {
    try {
      const params = new URLSearchParams({
        page,
        page_size: pageSize,
        ...filters,
      });

      const res = await api.get(`/${tenant}/api/agent/?${params.toString()}`);

      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to fetch agents");
    }
  }

  async function getTags() {
    try {
      const res = await api.get(`/${tenant}/api/agent/tags/`);
      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to fetch tags");
    }
  }

  async function createTag(data) {
    try {
      const res = await api.post(`/${tenant}/api/agent/tags/`, data);
      return res.data; // {id, name}
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to create tag");
    }
  }
  async function createAgent(data) {
    try {
      const res = await api.post(`/${tenant}/api/agent/`, data);
      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to create agent");
    }
  }

  async function updateAgent(agentId, data) {
    try {
      const res = await api.patch(`/${tenant}/api/agent/${agentId}/`, data);
      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to update agent");
    }
  }

  async function getAgentById(agentId) {
    try {
      const res = await api.get(`/${tenant}/api/agent/${agentId}/`);
      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to fetch agent details");
    }
  }

  async function deleteAgent(agentId) {
    try {
      await api.delete(`/${tenant}/api/agent/${agentId}/`);
      return true;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to delete agent");
    }
  }

  // Create Chat
  async function createChat(agentId) {
    try {
      const res = await api.post(`/${tenant}/api/chat/create/`, {
        agent_id: agentId,
      });
      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to create chat");
    }
  }

  // List Chats
  async function getChats(agentId) {
    try {
      const res = await api.get(`/${tenant}/api/chat/list/?agent_id=${agentId}`);
      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to fetch chats");
    }
  }

  // Get Messages
  async function getMessages(chatId) {
    try {
      const res = await api.get(`/${tenant}/api/chat/${chatId}/messages/`);
      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to fetch messages");
    }
  }

  // Send Message
  async function sendMessage(chatId, message) {
    try {
      const res = await api.post(`/${tenant}/api/chat/${chatId}/message/`, {
        message: message,
      });
      return res.data;
    } catch (err) {
      throw new Error(err.response?.data?.detail || "Failed to send message");
    }
  }

  async function forgotPassword(email) {
    if (!email) throw new Error("Email is required");

    try {
      const res = await api.post(`/${tenant}/users/forgot-password/`, { email });
      return res.data; // { detail: "Password reset email sent." }
    } catch (err) {
      throw new Error(
        err.response?.data?.detail || "Failed to send password reset email"
      );
    }
  }

  async function resetPassword({ uid, token, password }) {
    if (!uid || !token || !password) {
      throw new Error("UID, token, and new password are required");
    }

    try {
      const res = await api.post(`/${tenant}/users/reset-password/${uid}/${token}/`, {
        password,
      });
      return res.data; // { detail: "Password reset successful." }
    } catch (err) {
      throw new Error(
        err.response?.data?.detail || "Failed to reset password"
      );
    }
  }


  async function getMetrics(){
    try{
      const res = await api.get(`/${tenant}/api/metrics/`)
      return res.data
    }catch(err){
      throw new Error(
        err.response?.data?.detail || "Failed to fetch metrics"
      );
    }
  }


  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        login,
        logout,
        refresh,
        validateInvite,
        acceptInvite,
        fetchUsers,
        updateUser,
        getInvitedUsers,
        sendInvite,
        forgotPassword,
        resetPassword,
        getDocs,
        downloadDoc,
        updateDoc,
        deleteDoc,
        uploadDoc,
        getAgents,
        getTags,
        createTag,
        createAgent,
        getAgentById,
        updateAgent,
        deleteAgent,
        createChat,
        getChats,
        getMessages,
        sendMessage,
        getMetrics,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}