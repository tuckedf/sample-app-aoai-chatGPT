import React from 'react';

interface CustomButtonProps {
  onIdeaClick: (idea: string) => void;
  conversationId: string | undefined;
  children: React.ReactNode;
}

const CustomButton: React.FC<CustomButtonProps> = ({ onIdeaClick, conversationId, children }) => {
  const handleClick = () => {
    if (typeof children === 'string') {
      onIdeaClick(children);
    }
  };

  return (
    <button onClick={handleClick} data-conversation-id={conversationId}>
      {children}
    </button>
  );
};

export default CustomButton;