export async function scanFiles(files: any[], batchSize = 20) {
  if (!files || files.length === 0) return { results: [] };

  const url = `${import.meta.env.VITE_API_URL}/scan`;
  const results: any[] = [];
  const errors: Array<{ batch: number; error: unknown }> = [];

  const batches: any[][] = [];
  for (let i = 0; i < files.length; i += batchSize) {
    batches.push(files.slice(i, i + batchSize));
  }

  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(batch),
      });

      const data = await res.json();
      if (Array.isArray(data?.results)) results.push(...data.results);
    } catch (err) {
      console.error("Fetch error on batch", i + 1, err);
      errors.push({ batch: i + 1, error: err });
    }
  }

  return { results, errors }; // caller can optionally surface errors
}
