/* Home page route
 * Shows welcome message and links to main features
 */
export function HomePage() {
  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-4xl font-bold mb-4">Welcome to CAA</h2>
        <p className="text-xl text-slate-600 max-w-2xl">
          Clinical Analysis Assistant - Extract genetic information from research papers.
        </p>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-lg border border-slate-200 hover:border-slate-300 transition">
          <h3 className="text-lg font-semibold mb-2">📄 Papers</h3>
          <p className="text-slate-600">
            Upload and analyze research papers to extract patient data, variants, and phenotypes.
          </p>
        </div>

        <div className="bg-white p-6 rounded-lg border border-slate-200 hover:border-slate-300 transition">
          <h3 className="text-lg font-semibold mb-2">🔬 Analysis</h3>
          <p className="text-slate-600">
            AI-powered extraction pipeline processes papers and links data to HPO and genomic databases.
          </p>
        </div>
      </section>

      <section className="bg-blue-50 p-6 rounded-lg border border-blue-200">
        <h3 className="text-lg font-semibold mb-2">Getting Started</h3>
        <p className="text-slate-700 mb-4">
          Make sure the backend API is running on port 8000 before proceeding.
        </p>
        <code className="bg-white px-3 py-2 rounded text-sm font-mono text-slate-900">
          ./bin/api
        </code>
      </section>
    </div>
  )
}
