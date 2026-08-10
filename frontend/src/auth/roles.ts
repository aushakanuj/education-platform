/** Backend role strings from MeResponse.roles. */

export const ROLE_ADMIN = "administrator";
export const ROLE_TEACHER = "teacher";
export const ROLE_STUDENT = "student";

export type AppRole =
  | typeof ROLE_ADMIN
  | typeof ROLE_TEACHER
  | typeof ROLE_STUDENT;

/** Priority when a user has multiple roles: admin → teacher → student. */
const ROLE_PRIORITY: AppRole[] = [ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT];

export function hasRole(roles: readonly string[], role: string): boolean {
  return roles.includes(role);
}

/** First matching role by priority, or null if none of the known roles. */
export function primaryRole(roles: readonly string[]): AppRole | null {
  for (const role of ROLE_PRIORITY) {
    if (hasRole(roles, role)) {
      return role;
    }
  }
  return null;
}

/** Home path for the user's primary role. Students (and unknown) land on `/`. */
export function roleHome(roles: readonly string[]): string {
  const primary = primaryRole(roles);
  if (primary === ROLE_ADMIN) return "/admin";
  if (primary === ROLE_TEACHER) return "/teacher";
  return "/";
}
