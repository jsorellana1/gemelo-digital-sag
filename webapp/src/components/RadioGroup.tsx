interface Option { value: string; label: string; }

export default function RadioGroup({ name, label, value, options, onChange }: {
  name: string; label: string; value: string; options: Option[]; onChange: (v: string) => void;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      <div className="radio-row">
        {options.map((opt) => (
          <label key={opt.value} className="radio-option">
            <input
              type="radio" name={name} value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange(opt.value)}
            />
            {opt.label}
          </label>
        ))}
      </div>
    </div>
  );
}
