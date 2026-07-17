import { NavLink, useParams, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../../services/auth/useAuth";
import LoadingButton from "../LoadingButton";

export default function Sidebar({ collapsed }) {
  const { org, agentId, chatId } = useParams();
  const navigate = useNavigate();
  const { getChats, logout } = useAuth();

  const [chats, setChats] = useState([]);

  const isChatPage = !!agentId;

  useEffect(() => {
    if (!agentId) return;

    async function fetchChats() {
      try {
        const data = await getChats(agentId);
        setChats(data);
      } catch (err) {
        console.error(err);
      }
    }

    fetchChats();
  }, [agentId]);

  const linkClass = ({ isActive }) =>
    `flex items-center rounded-lg mb-2 transition-all duration-200
     ${collapsed ? "justify-center p-3" : "px-4 py-2"}
     ${
       isActive
         ? "bg-gray-900 text-white"
         : "text-gray-700 hover:bg-gray-100"
     }`;

  return (
    <div
      className={`
        ${collapsed ? "w-16" : "w-64"}
        bg-white border-r h-screen
        transition-all duration-300 ease-in-out
        flex flex-col
      `}
    >
      {/* 🔹 TOP SECTION */}
      <div className="p-3">
        {!collapsed && (
          <h1 className="text-xl font-semibold mb-6 px-2">
            AI Console
          </h1>
        )}

        <nav className="flex flex-col gap-1">
          <NavLink to={`/${org}/metrics`} className={linkClass}>
            <span>📊</span>
            {!collapsed && <span className="ml-3">Metrics</span>}
          </NavLink>

          <NavLink to={`/${org}/agents`} className={linkClass}>
            <span>🔧</span>
            {!collapsed && <span className="ml-3">Agents</span>}
          </NavLink>

          <NavLink to={`/${org}/docs`} className={linkClass}>
            <span>📄</span>
            {!collapsed && <span className="ml-3">Documents</span>}
          </NavLink>

          <NavLink to={`/${org}/profile`} className={linkClass}>
            <span>📊</span>
            {!collapsed && <span className="ml-3">Profile</span>}
          </NavLink>
          
        </nav>
      </div>

      {/* 🔥 SCROLLABLE SECTION */}
      <div className="flex-1 overflow-y-auto px-3">
        {isChatPage && !collapsed && (
          <div className="mt-4 border-t pt-4">
            <div className="flex justify-between items-center px-2 mb-2">
              <h2 className="text-sm font-semibold text-gray-500">
                Chats
              </h2>
              <button
                onClick={() =>
                  navigate(`/${org}/agents/${agentId}/`)
                }
                className="text-xs text-gray-500 hover:text-black"
              >
                +
              </button>
            </div>

            <div className="flex flex-col gap-1">
              {chats.map((chat) => (
                <div
                  key={chat.id}
                  onClick={() =>
                    navigate(`/${org}/agents/${agentId}/${chat.id}`)
                  }
                  className={`px-3 py-2 rounded-md cursor-pointer text-sm truncate
                    ${
                      chatId == chat.id
                        ? "bg-gray-900 text-white"
                        : "text-gray-600 hover:bg-gray-100"
                    }`}
                >
                  {chat.title || `Chat #${chat.id}`}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 🔻 FIXED LOGOUT */}
        <div className="p-3 border-t">
        {collapsed ? (
            <button
            onClick={logout}
            className="text-lg flex justify-center w-full"
            title="Logout"
            >
            ➜]
            </button>
        ) : (
            <LoadingButton
            text="Logout"
            loadingText="Logging out..."
            onClick={logout}
            />
        )}
        </div>
    </div>
  );
}