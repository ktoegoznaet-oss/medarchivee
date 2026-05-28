import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useProfileStore } from '@/stores/profile'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/views/profile/ProfileView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/analyses',
    name: 'analyses',
    component: () => import('@/views/analyses/AnalysesListView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/analyses/new',
    name: 'analyses-create',
    component: () => import('@/views/analyses/AnalysisCreateView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/analyses/:id(\\d+)',
    name: 'analyses-detail',
    component: () => import('@/views/analyses/AnalysisDetailView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/ai/chat',
    name: 'ai-chat',
    component: () => import('@/views/ai/ChatView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/settings/telegram',
    name: 'settings-telegram',
    component: () => import('@/views/settings/TelegramView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/onboarding',
    name: 'onboarding',
    component: () => import('@/views/onboarding/OnboardingWizard.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/auth/register',
    name: 'register',
    component: () => import('@/views/auth/RegisterView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/auth/verify-email',
    name: 'verify-email',
    component: () => import('@/views/auth/VerifyEmailView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/auth/login',
    name: 'login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/auth/recovery-phrase',
    name: 'recovery-phrase',
    component: () => import('@/views/auth/RecoveryPhraseView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/auth/forgot-password',
    name: 'forgot-password',
    component: () => import('@/views/auth/ForgotPasswordView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/tickets',
    name: 'tickets-list',
    component: () => import('@/views/tickets/TicketsListView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/tickets/:id(\\d+)',
    name: 'ticket-detail',
    component: () => import('@/views/tickets/TicketDetailView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/account',
    name: 'account-settings',
    component: () => import('@/views/account/AccountSettingsView.vue'),
    meta: { requiresAuth: true, requiresProfile: true },
  },
  {
    path: '/admin',
    component: () => import('@/views/admin/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      { path: '', redirect: { name: 'admin-dashboard' } },
      {
        path: 'dashboard',
        name: 'admin-dashboard',
        component: () => import('@/views/admin/DashboardView.vue'),
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/admin/UsersView.vue'),
      },
      {
        path: 'invites',
        name: 'admin-invites',
        component: () => import('@/views/admin/InvitesView.vue'),
      },
      {
        path: 'tickets',
        name: 'admin-tickets',
        component: () => import('@/views/admin/TicketsView.vue'),
      },
      {
        path: 'settings',
        name: 'admin-settings',
        component: () => import('@/views/admin/SettingsView.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.tryRestoreSession()

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { name: 'home' }
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'home' }
  }

  if (to.meta.requiresProfile && auth.isAuthenticated) {
    const profileStore = useProfileStore()
    if (!profileStore.profileChecked) {
      await profileStore.fetchProfile()
    }
    if (profileStore.profile === null) {
      return { name: 'onboarding' }
    }
  }

  return true
})

export default router
