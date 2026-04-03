import React from "react";
//currently working on azure s3 (install boto3)
//pip install google-api-python-client
//pip install azure-storage-blob

// const mockCloudSources = [
//   {
//     id: "cl-1",
//     provider: "AWS S3",
//     bucket: "s3://prod-data-lake",
//     objects: 124500,
//     size: "2.4 TB",
//     scanned: true,
//     pii_found: 3402,
//     region: "ap-south-1",
//   },
// ];


export default function CloudPanel() {
  const [loading, setLoading] = React.useState(false);
  const [cloudData, setCloudData] = React.useState([]);
  
  const scanCloud = async () => {
  try {
    setLoading(true);

    const res = await fetch("http://127.0.0.1:8000/scan-cloud", {
      method: "POST",
    });

    const data = await res.json();
    console.log("SCAN RESPONSE:", data);

    const formatted = data.results.map((file: any, index: number) => ({
      id: index,
      provider: "AWS S3",
      bucket: file.file,
      region: "ap-south-1",
      objects: 1,
      size: "—",
      scanned: true,
      pii_found: Object.values(file.pii).filter(Boolean).length,
    }));

    setCloudData(formatted);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/30">
          <h3 className="text-[13px] font-semibold text-foreground">
            Cloud Storage Sources
          </h3>
        </div>
        <button
          onClick={scanCloud}
          className="px-4 py-2 text-[12px] bg-primary text-white rounded-sm"
        >
          {loading ? "Scanning..." : "Scan Cloud"}
        </button>
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-border bg-muted/20">
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Provider
              </th>
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Bucket / Container
              </th>
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Region
              </th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Objects
              </th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Size
              </th>
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                Scanned
              </th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground text-[11px] uppercase tracking-wider">
                PII Found
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {cloudData.map((c) => (
              <tr key={c.id} className="hover:bg-muted/20">
                <td className="px-4 py-2.5">
                  <span
                    className={`px-2 py-0.5 text-[11px] font-medium rounded-sm ${
                      c.provider === "AWS S3"
                        ? "bg-warning/10 text-warning"
                        : c.provider === "Azure Blob"
                          ? "bg-primary/10 text-primary"
                          : c.provider === "GCP Storage"
                            ? "bg-destructive/10 text-destructive"
                            : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {c.provider}
                  </span>
                </td>
                <td className="px-4 py-2.5 font-mono text-[12px] text-foreground">
                  {c.bucket}
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">
                  {c.region}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-foreground">
                  {c.objects.toLocaleString()}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-foreground">
                  {c.size}
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className={`w-1.5 h-1.5 rounded-full inline-block mr-1.5 ${c.scanned ? "bg-primary" : "bg-muted-foreground"}`}
                  />
                  <span className="text-[12px] text-muted-foreground">
                    {c.scanned ? "Yes" : "Pending"}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right font-mono">
                  <span
                    className={
                      c.pii_found > 0
                        ? "text-warning font-medium"
                        : "text-muted-foreground"
                    }
                  >
                    {c.pii_found.toLocaleString()}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
            Total Objects
          </div>
          <div className="text-xl font-bold text-foreground mt-1">
            {cloudData
              .reduce((a, c) => a + c.objects, 0)
              .toLocaleString()}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
            PII Detected
          </div>
          <div className="text-xl font-bold text-warning mt-1">
            {cloudData
              .reduce((a, c) => a + c.pii_found, 0)
              .toLocaleString()}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
            Providers
          </div>
          <div className="text-xl font-bold text-foreground mt-1">
            {new Set(cloudData.map((c) => c.provider)).size}
          </div>
        </div>
        <div className="bg-card border border-border rounded-sm p-3">
          <div className="text-[11px] text-muted-foreground uppercase tracking-wider">
            Unscanned
          </div>
          <div className="text-xl font-bold text-destructive mt-1">
            {cloudData.filter((c) => !c.scanned).length}
          </div>
        </div>
      </div>
    </div>
  );
}
