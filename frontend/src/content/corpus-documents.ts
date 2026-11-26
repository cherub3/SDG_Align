// The 6 indexed documents. doc_id is "doc_" + the SHA-256 of the PDF (scripts/download_corpus.py), so these are exact.
const DOCS: Record<string, string> = {
  "2bfb8f4c19d6f3c9d77f18e545b3a7e55745a2a96c91dbe5f73822fc6bd2ad6c": "Cameroon: biodiversity and IPLC conservation",
  "6f1ac2315be2a47c98cd10289b475811e5fff8eb79b3be6219ebe718f3ee953a": "Ecuador: jaguar landscape connectivity",
  "d01bd4278178e388128443134b04a77fdd79fed307e5bf799d3ebebfec8cb2a4": "Ecuador: marine biodiversity",
  "e72e747170fa21c7f40d0c27e77cbf7ec23ea66b9448a13cd3548a69ad802eec": "Ecuador: biodiversity (dry forests)",
  "e75ba796c7d58cc1c27571b733bbe09cfc2afbfbce2271dd66ffbe2ca179500f": "Cuba: clean energy",
  "e2fd661744c7c3b66a02391da610a266a80068a43997a5e0d2568b4a9f404354": "Mozambique: planetGOLD",
}

export const INDEXED_DOCUMENT_COUNT = Object.keys(DOCS).length

export function documentTitle(docId: string): string {
  return DOCS[docId.replace(/^doc_/, "")] ?? docId
}
