BEGIN;

INSERT INTO departments (name, description, is_active) VALUES
('Engineering', 'Software development and engineering', TRUE),
('Quality Assurance', 'Software testing and quality assurance', TRUE),
('Operations', 'Business and project operations', TRUE),
('Human Resources', 'Employee and people management', TRUE)
ON CONFLICT (name) DO NOTHING;

INSERT INTO roles (name, description) VALUES
('ADMIN', 'Company administrator'),
('PROJECT_MANAGER', 'Creates and manages company projects'),
('TEAM_LEAD', 'Coordinates project teams and tasks'),
('EMPLOYEE', 'Works on assigned tasks')
ON CONFLICT (name) DO NOTHING;

INSERT INTO permissions (code, description) VALUES
('USER_MANAGE', 'Create and manage company employees'),
('ROLE_MANAGE', 'Manage roles and permissions'),
('PROJECT_CREATE', 'Create projects'),
('PROJECT_UPDATE', 'Update projects'),
('PROJECT_VIEW', 'View company projects'),
('MEMBER_ASSIGN', 'Manage project members'),
('TASK_CREATE', 'Create tasks'),
('TASK_ASSIGN', 'Assign tasks'),
('TASK_UPDATE_ASSIGNED', 'Update assigned tasks'),
('REPORT_VIEW', 'View project reports'),
('PROJECT_DELETE', 'Delete projects'),
('MILESTONE_STATUS_UPDATE', 'Update milestone status')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.name = 'ADMIN'
   OR (r.name = 'PROJECT_MANAGER' AND p.code IN
       ('PROJECT_CREATE','PROJECT_UPDATE','PROJECT_VIEW','MEMBER_ASSIGN','TASK_CREATE','TASK_ASSIGN','REPORT_VIEW','PROJECT_DELETE'))
   OR (r.name = 'TEAM_LEAD' AND p.code IN
       ('PROJECT_UPDATE','PROJECT_VIEW','TASK_CREATE','TASK_ASSIGN','TASK_UPDATE_ASSIGNED','MILESTONE_STATUS_UPDATE'))
   OR (r.name = 'EMPLOYEE' AND p.code IN ('PROJECT_VIEW','TASK_UPDATE_ASSIGNED'))
ON CONFLICT (role_id, permission_id) DO NOTHING;

COMMIT;

SELECT id, name FROM departments ORDER BY id;
SELECT id, name FROM roles ORDER BY id;
SELECT r.name AS role_name, p.code AS permission
FROM role_permissions rp
JOIN roles r ON r.id=rp.role_id
JOIN permissions p ON p.id=rp.permission_id
ORDER BY r.name, p.code;
