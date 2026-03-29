export async function scanFiles(files: any[]) {
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/scan`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(files),
    });

    const data = await res.json();
    console.log("Response:", data);
    return data;
  } catch (err) {
    console.error("Fetch error:", err);
  }
}