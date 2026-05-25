export interface User {
  id: string;
  name: string;
  avatar?: string;
  role: "demo" | "member" | "admin" | string;
}
