import React, { useState } from 'react';
import { Toggle } from '@fluentui/react';
import './ModelSwitch.css';

const ModelSwitch = ({ onModelChange }: { onModelChange: Function }) => {
    const [isChecked, setIsChecked] = useState(false);

    const handleToggleChange = (event: React.MouseEvent<HTMLElement>, checked?: boolean) => {
        setIsChecked(checked ?? false);
        const model = checked ? 'chatgpt-4.0' : 'chatgpt-3.5';
        onModelChange(model);
    };

    return (
        <div className="model-switch spacing">
            <Toggle
                onText="ChatGPT 4.0"
                offText="ChatGPT 3.5"
                checked={isChecked}
                onChange={handleToggleChange}
            />
        </div>
    );
};

export default ModelSwitch;