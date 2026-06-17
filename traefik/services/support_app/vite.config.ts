import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import legacy from '@vitejs/plugin-legacy';

export default defineConfig({
  plugins: [
    react(),
    // Transpile down to Chrome 51 / Android 6 WebView
    legacy({
      targets: ['Chrome >= 51', 'Firefox >= 54', 'Edge >= 15', 'Android >= 6'],
      additionalLegacyPolyfills: ['core-js/stable'],
      renderLegacyChunks: true,
      modernPolyfills: true,
    }),
  ],
  server: {
    port: 5173,
    // Proxy Odoo JSON-RPC calls in dev to avoid CORS issues
    proxy: {
      '/web': {
        target: process.env.ODOO_TARGET_URL ?? process.env.VITE_ODOO_URL ?? 'http://localhost:8070',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    minify: 'terser',
    sourcemap: true,
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: {
          // Vendor chunks for better caching
          'vendor-react': ['react', 'react-dom'],
          'vendor-ui': ['lucide-react', 'clsx'],
          'vendor-utils': ['axios', 'date-fns', 'zustand'],
        },
      },
    },
  },
});
