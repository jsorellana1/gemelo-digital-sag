interface DualInputProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onChange: (value: number) => void;
}

// Slider + input numerico sincronizados: el usuario puede arrastrar o
// digitar el valor directamente (requisito explicito, no solo slider).
export default function DualInput({ label, value, min, max, step, suffix, onChange }: DualInputProps) {
  return (
    <div className="field">
      <label>{label}</label>
      <div className="dual">
        <input
          type="range" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <div className="dual-num">
          <input
            type="number" min={min} max={max} step={step} value={value}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (!Number.isNaN(v)) onChange(v);
            }}
          />
          {suffix && <span className="suffix">{suffix}</span>}
        </div>
      </div>
    </div>
  );
}
