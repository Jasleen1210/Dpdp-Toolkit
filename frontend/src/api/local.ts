export async function scanFiles(files: any[], batchSize = 20) {
  if (!files || files.length === 0) {
    console.warn("[LocalScan][API] Skipping /scan call: empty payload");
    return { results: [] };
  }

  const url = `${import.meta.env.VITE_API_URL}/scan`;
  console.log("[LocalScan][API] Starting scan request", {
    url,
    totalFiles: files.length,
    batchSize,
  });
  const results: any[] = [];
  const errors: Array<{ batch: number; error: unknown }> = [];

  const batches: any[][] = [];
  for (let i = 0; i < files.length; i += batchSize) {
    batches.push(files.slice(i, i + batchSize));
  }

  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    try {
      console.log("[LocalScan][API] Sending batch", {
        batch: i + 1,
        batchFiles: batch.length,
        names: batch.map((f: any) => f?.name),
      });

      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(batch),
      });

      console.log("[LocalScan][API] Batch response", {
        batch: i + 1,
        ok: res.ok,
        status: res.status,
      });

      const data = await res.json();
      if (Array.isArray(data?.results)) results.push(...data.results);
    } catch (err) {
      console.error("Fetch error on batch", i + 1, err);
      errors.push({ batch: i + 1, error: err });
    }
  }

  console.log("[LocalScan][API] Completed scan request", {
    resultCount: results.length,
    errorBatches: errors.length,
  });

  return { results, errors }; // caller can optionally surface errors
}
