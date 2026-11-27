// Vite's `?url` import of pdf.js's worker gives the address of the built file (src/utils/pdfjsLoader.ts).
declare module 'pdfjs-dist/build/pdf.worker.min.mjs?url' {
  const src: string;
  export default src;
}
