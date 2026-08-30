/* Zustand UI state store
 * Manages global UI state like modals, notifications, sidebar visibility, etc.
 *
 * Usage:
 *   import { useUIStore } from '@/stores/ui'
 *   const { isModalOpen, openModal } = useUIStore()
 */
import { create } from 'zustand'

interface UIState {
  isMenuOpen: boolean
  toggleMenu: () => void
  closeMenu: () => void
}

export const useUIStore = create<UIState>((set) => ({
  isMenuOpen: false,
  toggleMenu: () => set((state) => ({ isMenuOpen: !state.isMenuOpen })),
  closeMenu: () => set({ isMenuOpen: false }),
}))
