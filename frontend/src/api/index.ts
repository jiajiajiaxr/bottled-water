export { API_BASE, request, requestWithTimeout, requestFile, wait, eventPayload } from "./client";
export type { StreamAssistantHandlers } from "./client";

export {
  login,
  register,
  updateProfile,
  changePassword,
  demoLogin,
  me,
  logout,
} from "./auth";

export {
  conversations,
  createConversation,
  createConversationWithAgents,
  updateConversation,
  deleteConversation,
  addParticipants,
  removeParticipant,
} from "./conversation";

export {
  messages,
  sendMessage,
  streamAssistantReply,
  assistantReply,
  cancelAssistantReply,
} from "./message";

export { tasks, createBackgroundTask, cancelTask } from "./task";

export {
  artifact,
  artifactById,
  saveArtifact,
  exportArtifact,
} from "./artifact";

export {
  conversationWorkflow,
  saveConversationWorkflow,
  generateConversationWorkflow,
  workflowRuns,
  startWorkflowRun,
  updateWorkflowNode,
} from "./workflow";

export { deploy } from "./deploy";

export {
  agents,
  createAgent,
  updateAgent,
  deleteAgent,
  parseCapabilities,
  generateAgentConfig,
  generateAgent,
  testAgent,
} from "./agent";

export { uploadFile, files, previewFile } from "./file";

export {
  knowledgeBases,
  createKnowledgeBase,
  importKnowledgeText,
  retrieveKnowledge,
} from "./knowledge";

export {
  workspaces,
  createWorkspace,
  projects,
  createProject,
  saveProjectFile,
} from "./workspace";

export {
  workspaceFileTree,
  previewWorkspaceFile,
  downloadWorkspaceFile,
  deleteWorkspaceFile,
  renameWorkspaceFile,
  createWorkspaceFolder,
  moveWorkspaceFiles,
  favoriteWorkspaceFile,
  bulkDeleteWorkspaceFiles,
} from "./workspaceFile";

export {
  modelProviders,
  createModelProvider,
  modelConfigs,
  createModelConfig,
  testModel,
} from "./model";

export {
  mcpServers,
  createMcpServer,
  importMcpServer,
  probeMcpServer,
  invokeMcpTool,
  deleteMcpServer,
  mcpInvocations,
} from "./mcp";

export {
  skills,
  createSkill,
  importMcpAsSkill,
  generateSkill,
  testSkill,
  deleteSkill,
} from "./skill";

export {
  tools,
  createTool,
  generateTool,
  invokeTool,
  deleteTool,
} from "./tool";

export {
  sandboxes,
  createSandbox,
  runSandboxCommand,
} from "./sandbox";

export {
  remoteConnections,
  createRemoteConnection,
  connectRemote,
} from "./remote";

export {
  auditLogs,
  auditStats,
  securityRoles,
  securityPermissions,
  securityUsers,
} from "./security";

// 兼容旧版 api 对象用法
import * as auth from "./auth";
import * as conversation from "./conversation";
import * as message from "./message";
import * as task from "./task";
import * as artifact from "./artifact";
import * as workflow from "./workflow";
import * as deploy from "./deploy";
import * as agent from "./agent";
import * as file from "./file";
import * as knowledge from "./knowledge";
import * as workspace from "./workspace";
import * as workspaceFile from "./workspaceFile";
import * as model from "./model";
import * as mcp from "./mcp";
import * as skill from "./skill";
import * as tool from "./tool";
import * as sandbox from "./sandbox";
import * as remote from "./remote";
import * as security from "./security";

export const api = {
  ...auth,
  ...conversation,
  ...message,
  ...task,
  ...artifact,
  ...workflow,
  ...deploy,
  ...agent,
  ...file,
  ...knowledge,
  ...workspace,
  ...workspaceFile,
  ...model,
  ...mcp,
  ...skill,
  ...tool,
  ...sandbox,
  ...remote,
  ...security,
};
