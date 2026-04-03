import React, { useState } from "react";

export default function RequestPanel() {
  const [type, setType] = useState("ACCESS");
  const [identifier, setIdentifier] = useState("");
  const [newValue, setNewValue] = useState("");
  const [result, setResult] = useState<any>(null);

  const handleSubmit = async () => {
    const res = await fetch("http://127.0.0.1:8000/dpdp/request", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        type,
        identifier,
        new_value: newValue,
      }),
    });

    const data = await res.json();
    setResult(data);
  };

  return (
    <div className="p-4 border rounded">
      <h3 className="font-bold mb-2">DPDP Request</h3>

      <select onChange={(e) => setType(e.target.value)}>
        <option>ACCESS</option>
        <option>DELETE</option>
        <option>UPDATE</option>
      </select>

      <input
        placeholder="Enter email/phone"
        onChange={(e) => setIdentifier(e.target.value)}
        className="border p-1 ml-2"
      />

      {type === "UPDATE" && (
        <input
          placeholder="New value"
          onChange={(e) => setNewValue(e.target.value)}
          className="border p-1 ml-2"
        />
      )}

      <button onClick={handleSubmit} className="ml-2 bg-blue-500 text-white px-3 py-1">
        Submit
      </button>

      {result && (
        <pre className="mt-3 text-xs bg-gray-100 p-2">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}