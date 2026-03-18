window.MessengerApp = window.MessengerApp || {};
window.MessengerApp.features = window.MessengerApp.features || {};
window.MessengerApp.features.auth = {
    api: window.api,
    loadRuntimeConfig: window.loadRuntimeConfig,
    showAuthError: window.showAuthError,
    showAuthSuccess: window.showAuthSuccess,
    hideAuthError: window.hideAuthError,
    showRegisterForm: window.showRegisterForm,
    showLoginForm: window.showLoginForm,
    doLogin: window.doLogin,
    doRegister: window.doRegister,
    logout: window.logout,
    checkSession: window.checkSession,
    calculatePasswordStrength: window.calculatePasswordStrength,
    updatePasswordStrength: window.updatePasswordStrength,
    updateInputValidation: window.updateInputValidation,
    updateStepIndicator: window.updateStepIndicator,
    validateStep: window.validateStep
};

